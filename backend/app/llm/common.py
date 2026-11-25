"""Provider-independent pieces: prompts, quiz schema, citation bookkeeping."""

import random
import re

from ..retrieval import tokenize
from ..store import Chunk


class LLMError(Exception):
    """An LLM failure translated into an HTTP status and a message a student can act on."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


# --------------------------------------------------------------------------- prompts

ASK_GUIDANCE = """You are StudyLens, a study assistant. You answer a student's questions using their own course materials, which are given to you as excerpts (each excerpt comes from a specific page of a file).

How to answer:
- Base the answer on the excerpts and cite them.
- Cite an excerpt only for statements that excerpt actually makes. Don't attach a citation to an inference, a contrast the notes don't state, or anything from general knowledge.
- Start with a short, direct answer, then give the key explanation, steps or example a good TA would add. Keep it focused; no padding.
- If the excerpts don't contain the answer, say so plainly and suggest what the student could look for. Only use general knowledge if it is needed to make the material understandable, and when you do, say that this part is not from their materials.
- Use Markdown for lists, emphasis and code. Write math in LaTeX: $...$ inline, $$...$$ for display equations."""

QUIZ_SYSTEM = """You write multiple-choice practice questions for a student, based strictly on excerpts from their course materials.

Rules:
- Every question must be answerable from the excerpts. Set source_id to the id of the excerpt that supports it.
- Test understanding (applying, comparing, explaining why), not trivia like page titles or who said what.
- Exactly 4 options per question, one clearly correct. Distractors should be plausible misconceptions, not jokes.
- Do not use "all of the above" or "none of the above".
- The explanation says why the correct option is right and, briefly, why the most tempting distractor is wrong.
- Options are shuffled before the student sees them, so in explanations refer to options by what they say, never by letter, number or position.
- Cover different parts of the material; don't ask the same thing twice.
- Write math in LaTeX: $...$ inline."""

QUIZ_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "correct_option": {"type": "integer"},
                    "explanation": {"type": "string"},
                    "source_id": {"type": "string"},
                },
                "required": ["question", "options", "correct_option", "explanation", "source_id"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}

DIFFICULTY_HINTS = {
    "easy": "Difficulty: easy. Check that the student knows core definitions and main ideas.",
    "medium": "Difficulty: medium. Mix recall with applying concepts to small examples.",
    "hard": "Difficulty: hard. Require multi-step reasoning, edge cases, or connecting two ideas.",
}


def tag_excerpts(chunks: list[Chunk]) -> tuple[dict[str, Chunk], str]:
    """Give each chunk an id (S1, S2, ...) and render them as tagged excerpts."""
    by_id = {f"S{i + 1}": c for i, c in enumerate(chunks)}
    text = "\n\n".join(
        f'<excerpt id="{sid}" file="{c.doc_name}" page="{c.page}">\n{c.text}\n</excerpt>' for sid, c in by_id.items()
    )
    return by_id, text


def quiz_prompt(chunks: list[Chunk], num_questions: int, difficulty: str, topic: str | None) -> tuple[dict[str, Chunk], str]:
    by_id, excerpts = tag_excerpts(chunks)
    focus = f"Focus on this topic: {topic}" if topic else "Cover the most important ideas across the excerpts."
    prompt = (
        f"{excerpts}\n\nWrite {num_questions} multiple-choice questions from these excerpts.\n"
        f"{focus}\n{DIFFICULTY_HINTS.get(difficulty, DIFFICULTY_HINTS['medium'])}\n"
        "correct_option is the 0-based index of the correct option."
    )
    return by_id, prompt


def postprocess_quiz(data: dict, by_id: dict[str, Chunk], num_questions: int) -> list[dict]:
    """Validate model output, drop malformed items, and shuffle options to remove position bias."""
    questions = []
    for q in data.get("questions", []) if isinstance(data, dict) else []:
        if not isinstance(q, dict) or not str(q.get("question", "")).strip():
            continue
        options = [o for o in q.get("options", []) if isinstance(o, str) and o.strip()]
        correct = q.get("correct_option")
        if len(options) < 2 or not isinstance(correct, int) or not 0 <= correct < len(options):
            continue
        order = list(range(len(options)))
        random.shuffle(order)
        src = by_id.get(str(q.get("source_id", "")).strip())
        questions.append(
            {
                "question": q["question"],
                "options": [options[i] for i in order],
                "answer_index": order.index(correct),
                "explanation": q.get("explanation", ""),
                "source": {"doc_id": src.doc_id, "doc_name": src.doc_name, "page": src.page} if src else None,
            }
        )
    return questions[:num_questions]


# --------------------------------------------------------------------------- citations


class SourceTracker:
    """Numbers cited pages [1], [2], ... in order of first citation and collects quotes.

    Sources are per page, not per chunk: two passages from the same page are one source.
    """

    def __init__(self):
        self._numbers: dict[tuple[str, int], int] = {}
        self.sources: list[dict] = []

    def add(self, chunk: Chunk, quote: str = "") -> int:
        key = (chunk.doc_id, chunk.page)
        if key not in self._numbers:
            self._numbers[key] = len(self.sources) + 1
            self.sources.append(
                {"n": self._numbers[key], "doc_id": chunk.doc_id, "doc_name": chunk.doc_name, "page": chunk.page, "quotes": []}
            )
        n = self._numbers[key]
        quote = quote.strip()
        quotes = self.sources[n - 1]["quotes"]
        if quote and not any(quote in q for q in quotes):
            # Drop shorter quotes the new one contains, so overlapping passages show once
            quotes[:] = [q for q in quotes if q not in quote] + [quote]
        return n


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def best_quote(chunk: Chunk, claim: str, max_len: int = 400) -> str:
    """Pick the passage (1-2 consecutive sentences) of the chunk that best supports the claim.

    Scored by word overlap with the claim. Two-sentence windows catch the common case
    where the subject is named in one sentence and the fact is stated in the next.
    """
    claim_terms = set(tokenize(claim[-400:]))
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(chunk.text) if s.strip()]
    if not sentences:
        return chunk.text[:max_len]
    windows = sentences + [f"{a} {b}" for a, b in zip(sentences, sentences[1:])]
    windows = [w for w in windows if len(w) > 20] or windows
    if not claim_terms:
        return windows[0][:max_len]

    def score(w: str) -> tuple[int, int]:
        return len(claim_terms & set(tokenize(w))), -len(w)  # most overlap, then shortest

    best = max(windows, key=score)
    return best if len(best) <= max_len else best[: max_len - 1] + "…"


# Matches [S1], [S1, S3], [S2; S4]
_MARKER = re.compile(r"\[\s*(S\d+(?:\s*[,;]\s*S\d+)*)\s*\]")


def parse_marked_answer(text: str, by_id: dict[str, Chunk]) -> tuple[list[dict], list[dict]]:
    """Turn an answer containing [S#] markers into cited segments.

    Ids that weren't in the retrieved excerpts are dropped, so a model can't cite a
    source that doesn't exist.
    """
    tracker = SourceTracker()
    segments: list[dict] = []
    pos = 0
    for m in _MARKER.finditer(text):
        before = text[pos : m.start()]
        if not before.strip() and segments:
            target = segments[-1]  # back-to-back markers like [S1][S3] cite the same text
        else:
            target = {"text": before.rstrip(" "), "cites": []}
            segments.append(target)
        for sid in re.findall(r"S\d+", m.group(1)):
            chunk = by_id.get(sid)
            if chunk is None:
                continue
            n = tracker.add(chunk, best_quote(chunk, target["text"]))
            if n not in target["cites"]:
                target["cites"].append(n)
        pos = m.end()
    if pos < len(text):
        segments.append({"text": text[pos:], "cites": []})
    return segments, tracker.sources
