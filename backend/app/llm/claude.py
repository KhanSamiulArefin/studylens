"""Claude provider: uses Claude's native citations API and JSON-schema structured outputs."""

import json

import anthropic

from ..config import CLAUDE_MODEL
from ..store import Chunk
from .common import ASK_GUIDANCE, QUIZ_SCHEMA, QUIZ_SYSTEM, LLMError, SourceTracker, postprocess_quiz, quiz_prompt

# Server-side refusal fallback: if the primary model declines a request, the API
# re-runs it on a fallback model inside the same call.
BETAS = ["server-side-fallback-2026-07-01"]

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _create(**kwargs):
    try:
        response = _get_client().beta.messages.create(
            model=CLAUDE_MODEL, max_tokens=16000, betas=BETAS, fallbacks="default", **kwargs
        )
    except anthropic.AuthenticationError:
        raise LLMError(401, "The Anthropic API key was rejected. Check ANTHROPIC_API_KEY in backend/.env.")
    except anthropic.PermissionDeniedError:
        raise LLMError(403, "This Anthropic API key doesn't have access to the configured model.")
    except anthropic.NotFoundError:
        raise LLMError(404, f"Model '{CLAUDE_MODEL}' wasn't found. Check CLAUDE_MODEL in backend/.env.")
    except anthropic.RateLimitError:
        raise LLMError(429, "Rate limited by the Anthropic API. Wait a moment and try again.")
    except anthropic.BadRequestError as e:
        raise LLMError(400, f"The Anthropic API rejected the request: {e.message}")
    except anthropic.APIStatusError as e:
        raise LLMError(502, f"Anthropic API error ({e.status_code}). Try again shortly.")
    except anthropic.APIConnectionError:
        raise LLMError(503, "Couldn't reach the Anthropic API. Check your internet connection.")
    if response.stop_reason == "refusal":
        raise LLMError(422, "Claude declined this request.")
    return response


def _doc_block(chunk: Chunk) -> dict:
    return {
        "type": "document",
        "source": {"type": "text", "media_type": "text/plain", "data": chunk.text},
        "title": f"{chunk.doc_name}, page {chunk.page}",
        "citations": {"enabled": True},
    }


def answer_question(question: str, chunks: list[Chunk]) -> dict:
    content = [_doc_block(c) for c in chunks]
    content.append({"type": "text", "text": question})
    response = _create(
        output_config={"effort": "medium"},
        system=ASK_GUIDANCE,
        messages=[{"role": "user", "content": content}],
    )

    tracker = SourceTracker()
    segments = []
    for block in response.content:
        if block.type != "text":
            continue  # thinking / fallback marker blocks
        cites: list[int] = []
        for cit in block.citations or []:
            idx = getattr(cit, "document_index", None)
            if idx is None or not 0 <= idx < len(chunks):
                continue
            n = tracker.add(chunks[idx], getattr(cit, "cited_text", "") or "")
            if n not in cites:
                cites.append(n)
        segments.append({"text": block.text, "cites": cites})
    return {"segments": segments, "sources": tracker.sources, "model": response.model}


def generate_quiz(chunks: list[Chunk], num_questions: int, difficulty: str, topic: str | None) -> dict:
    by_id, prompt = quiz_prompt(chunks, num_questions, difficulty, topic)
    response = _create(
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": QUIZ_SCHEMA}},
        system=QUIZ_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise LLMError(502, "Claude returned a quiz in an unexpected format. Try again.")
    return {"questions": postprocess_quiz(data, by_id, num_questions), "model": response.model}
