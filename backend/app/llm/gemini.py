"""Gemini provider (free tier available).

Gemini has no document-citations API, so excerpts are tagged S1, S2, ... and the model
is asked to cite them inline as [S#]. The markers are then parsed and checked against
the retrieved excerpts in common.parse_marked_answer.
"""

import json

from google import genai
from google.genai import errors, types

from ..config import GEMINI_FALLBACK_MODELS, GEMINI_KEY, GEMINI_MODEL
from ..store import Chunk
from .common import ASK_GUIDANCE, QUIZ_SCHEMA, QUIZ_SYSTEM, LLMError, parse_marked_answer, postprocess_quiz, quiz_prompt, tag_excerpts

ASK_SYSTEM = (
    ASK_GUIDANCE
    + """

Citing: each excerpt has an id like S1. Right after each sentence or bullet that uses an excerpt, put its id in square brackets, e.g. [S2] or [S1][S4]. Only cite ids that appear in the excerpts. Don't add a separate sources list at the end."""
)

# The SDK runs on httpx or its fork httpx2, depending on what's installed; catch network errors from either.
_TIMEOUT_ERRORS: tuple[type[Exception], ...] = ()
_TRANSPORT_ERRORS: tuple[type[Exception], ...] = ()
for _mod in ("httpx", "httpx2"):
    try:
        _lib = __import__(_mod)
        _TIMEOUT_ERRORS += (_lib.TimeoutException,)
        _TRANSPORT_ERRORS += (_lib.TransportError,)
    except (ImportError, AttributeError):
        pass

# An overloaded free-tier model can take a minute or more to answer. Rather than wait,
# give each model this long and then move on to the next one.
REQUEST_TIMEOUT_MS = 20_000  # normal answers take ~5-12s

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(
            api_key=GEMINI_KEY,
            http_options=types.HttpOptions(
                timeout=REQUEST_TIMEOUT_MS,
                # No SDK-level retries: falling back to another model recovers faster than retrying a busy one
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
    return _client


def _models_to_try() -> list[str]:
    return list(dict.fromkeys([GEMINI_MODEL, *GEMINI_FALLBACK_MODELS]))


def _generate(prompt: str, config: types.GenerateContentConfig) -> tuple[str, str]:
    """Call Gemini, falling back to the next model when one is overloaded or rate-limited.

    Returns (text, model that answered).
    """
    last_busy: errors.APIError | None = None
    timed_out = False
    for model in _models_to_try():
        try:
            response = _get_client().models.generate_content(model=model, contents=prompt, config=config)
        except errors.ClientError as e:
            msg = (e.message or "").lower()
            if e.code in (401, 403) or "api key" in msg:
                raise LLMError(401, "The Gemini API key was rejected. Check GEMINI_API_KEY in backend/.env.")
            if e.code in (404, 429):  # model unavailable to this key, or its quota used up: try the next one
                last_busy = e
                continue
            raise LLMError(400, f"The Gemini API rejected the request: {e.message}")
        except errors.ServerError as e:
            if e.code in (500, 503, 504):  # overloaded / transient: try the next model
                last_busy = e
                continue
            raise LLMError(502, f"Gemini API error ({e.code}). Try again shortly.")
        except _TIMEOUT_ERRORS:  # model too slow (usually overloaded): try the next one
            timed_out = True
            continue
        except _TRANSPORT_ERRORS:
            raise LLMError(503, "Couldn't reach the Gemini API. Check your internet connection.")
        return _response_text(response), model

    if timed_out and last_busy is None:
        raise LLMError(504, "Gemini is responding very slowly right now (free tier). Try again in a minute.")
    if last_busy is not None and last_busy.code == 429:
        raise LLMError(429, "Hit the Gemini free-tier rate limit on every model. Wait a minute and try again.")
    if last_busy is not None and last_busy.code == 404:
        raise LLMError(404, "None of the configured Gemini models are available. Check GEMINI_MODEL in backend/.env.")
    raise LLMError(503, "All Gemini models are busy right now (free tier). Try again in a minute.")


def _response_text(response: types.GenerateContentResponse) -> str:
    text = response.text
    if not text:
        reason = ""
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            reason = f" ({response.prompt_feedback.block_reason})"
        elif response.candidates and response.candidates[0].finish_reason:
            reason = f" ({response.candidates[0].finish_reason})"
        raise LLMError(422, f"Gemini returned no answer{reason}. Try rephrasing.")
    return text


def answer_question(question: str, chunks: list[Chunk]) -> dict:
    by_id, excerpts = tag_excerpts(chunks)
    text, model = _generate(
        f"{excerpts}\n\nQuestion: {question}",
        types.GenerateContentConfig(system_instruction=ASK_SYSTEM),
    )
    segments, sources = parse_marked_answer(text, by_id)
    return {"segments": segments, "sources": sources, "model": model}


def generate_quiz(chunks: list[Chunk], num_questions: int, difficulty: str, topic: str | None) -> dict:
    by_id, prompt = quiz_prompt(chunks, num_questions, difficulty, topic)
    text, model = _generate(
        prompt,
        types.GenerateContentConfig(
            system_instruction=QUIZ_SYSTEM,
            response_mime_type="application/json",
            response_json_schema=QUIZ_SCHEMA,
        ),
    )
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise LLMError(502, "Gemini returned a quiz in an unexpected format. Try again.")
    return {"questions": postprocess_quiz(data, by_id, num_questions), "model": model}
