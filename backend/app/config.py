import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent

load_dotenv(BACKEND_DIR / ".env")

DATA_DIR = Path(os.getenv("STUDYLENS_DATA_DIR", BACKEND_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
INDEX_PATH = DATA_DIR / "index.json"
FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"

MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# Retrieval
ASK_TOP_K = 8
QUIZ_TOP_K = 10

# --------------------------------------------------------------------------- LLM provider


def _env(*names: str) -> str:
    for n in names:
        v = (os.getenv(n) or "").strip()
        if v:
            return v
    return ""


CLAUDE_MODEL = _env("CLAUDE_MODEL") or "claude-opus-5-5"
GEMINI_MODEL = _env("GEMINI_MODEL") or "gemini-3.8-flash"
# Free-tier models are often briefly overloaded (503) or rate-limited (429); these are tried in order.
GEMINI_FALLBACK_MODELS = [
    m.strip() for m in (_env("GEMINI_FALLBACK_MODELS") or "gemini-3.6-flash,gemini-3.5-flash-lite").split(",") if m.strip()
]

GEMINI_KEY = _env("GEMINI_API_KEY", "GOOGLE_API_KEY")
CLAUDE_KEY_SET = bool(_env("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"))


def _pick_provider() -> str:
    explicit = _env("LLM_PROVIDER").lower()
    if explicit in ("claude", "gemini"):
        return explicit
    # Not set: use whichever provider has a key, preferring the free one
    if GEMINI_KEY:
        return "gemini"
    if CLAUDE_KEY_SET:
        return "claude"
    return "gemini"


PROVIDER = _pick_provider()
MODEL = CLAUDE_MODEL if PROVIDER == "claude" else GEMINI_MODEL
KEY_ENV = "ANTHROPIC_API_KEY" if PROVIDER == "claude" else "GEMINI_API_KEY"


def api_key_configured() -> bool:
    return CLAUDE_KEY_SET if PROVIDER == "claude" else bool(GEMINI_KEY)
