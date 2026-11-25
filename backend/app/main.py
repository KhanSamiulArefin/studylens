from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import llm
from .config import (
    ASK_TOP_K,
    FRONTEND_DIST,
    INDEX_PATH,
    KEY_ENV,
    MAX_UPLOAD_BYTES,
    MODEL,
    PROVIDER,
    QUIZ_TOP_K,
    UPLOAD_DIR,
    api_key_configured,
)
from .ingest import extract_pages
from .store import Store

app = FastAPI(title="StudyLens API")
store = Store(INDEX_PATH)


@app.middleware("http")
async def revalidate_html(request, call_next):
    """Make browsers re-check index.html so a new build shows up on reload.

    Built JS/CSS under /assets have content-hashed names, so they can stay cached.
    """
    response = await call_next(request)
    if not request.url.path.startswith(("/api/", "/assets/")):
        response.headers["Cache-Control"] = "no-cache"
    return response


# --------------------------------------------------------------------------- helpers


def _call_llm(fn, *args):
    if not api_key_configured():
        raise HTTPException(503, f"No API key configured. Add {KEY_ENV} to backend/.env and restart the server.")
    try:
        return fn(*args)
    except llm.LLMError as e:
        raise HTTPException(e.status, e.message)


# --------------------------------------------------------------------------- routes


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "provider": PROVIDER,
        "model": MODEL,
        "api_key_configured": api_key_configured(),
        "key_env": KEY_ENV,
    }


@app.get("/api/documents")
def list_documents():
    return [d.__dict__ for d in store.documents()]


@app.post("/api/documents", status_code=201)
def upload_document(file: UploadFile = File(...)):
    name = Path(file.filename or "document.pdf").name
    if not name.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported.")

    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is larger than 50 MB.")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "That file doesn't look like a valid PDF.")

    doc_id = store.new_id()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = UPLOAD_DIR / f"{doc_id}.pdf"
    path.write_bytes(data)

    try:
        pages = extract_pages(path)
    except Exception:
        path.unlink(missing_ok=True)
        raise HTTPException(400, "Couldn't read this PDF. It may be encrypted or corrupted.")

    if not any(p.strip() for p in pages):
        path.unlink(missing_ok=True)
        raise HTTPException(
            422, "No selectable text found in this PDF. It's probably scanned images; OCR support is on the roadmap."
        )

    return store.add_document(doc_id, name, pages).__dict__


@app.delete("/api/documents/{doc_id}", status_code=204)
def delete_document(doc_id: str):
    if not store.delete_document(doc_id):
        raise HTTPException(404, "Document not found.")
    (UPLOAD_DIR / f"{doc_id}.pdf").unlink(missing_ok=True)


@app.get("/api/documents/{doc_id}/file")
def get_document_file(doc_id: str):
    doc = store.get_document(doc_id)
    path = UPLOAD_DIR / f"{doc_id}.pdf"
    if not doc or not path.exists():
        raise HTTPException(404, "Document not found.")
    safe_name = doc.name.encode("ascii", "ignore").decode().replace('"', "") or "document.pdf"
    return FileResponse(path, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{safe_name}"'})


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    doc_ids: list[str] | None = None


@app.post("/api/ask")
def ask(req: AskRequest):
    if not store.documents():
        raise HTTPException(400, "Upload some course materials first.")
    chunks = store.search_with_fallback(req.question, k=ASK_TOP_K, doc_ids=req.doc_ids)
    if not chunks:
        return {
            "segments": [
                {
                    "text": "I couldn't find anything in your materials that matches this question. "
                    "Try using the terms your lecture slides use, or upload the relevant notes.",
                    "cites": [],
                }
            ],
            "sources": [],
            "retrieved": [],
        }
    result = _call_llm(llm.answer_question, req.question.strip(), chunks)
    result["retrieved"] = [{"doc_name": c.doc_name, "page": c.page} for c in chunks]
    return result


class QuizRequest(BaseModel):
    topic: str | None = Field(default=None, max_length=300)
    num_questions: int = Field(default=5, ge=1, le=10)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    doc_ids: list[str] | None = None


@app.post("/api/quiz")
def quiz(req: QuizRequest):
    if not store.documents():
        raise HTTPException(400, "Upload some course materials first.")
    topic = (req.topic or "").strip() or None
    chunks = store.search(topic, k=QUIZ_TOP_K, doc_ids=req.doc_ids) if topic else store.sample(QUIZ_TOP_K, req.doc_ids)
    if not chunks:
        raise HTTPException(404, f'Nothing in your materials matches "{topic}". Try a different topic.')
    return _call_llm(llm.generate_quiz, chunks, req.num_questions, req.difficulty, topic)


# Serve the built React app (npm run build) from the same server in production.
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
