"""LLM facade: picks the provider from config (LLM_PROVIDER) and exposes one interface."""

from ..config import PROVIDER
from .common import LLMError

if PROVIDER == "claude":
    from . import claude as _impl
else:
    from . import gemini as _impl

answer_question = _impl.answer_question
generate_quiz = _impl.generate_quiz

__all__ = ["LLMError", "answer_question", "generate_quiz"]
