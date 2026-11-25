"""Document + chunk storage, persisted as a JSON file, with a cached BM25 index."""

import json
import random
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .ingest import chunk_text
from .retrieval import BM25


@dataclass
class Chunk:
    id: str
    doc_id: str
    doc_name: str
    page: int  # 1-indexed
    text: str


@dataclass
class Document:
    id: str
    name: str
    pages: int
    chunk_count: int
    uploaded_at: str


class Store:
    def __init__(self, index_path: Path):
        self.index_path = index_path
        self._lock = threading.Lock()
        self._docs: dict[str, Document] = {}
        self._chunks: list[Chunk] = []
        self._bm25: BM25 | None = None
        self._load()

    # ---------- persistence ----------
    def _load(self) -> None:
        if not self.index_path.exists():
            return
        data = json.loads(self.index_path.read_text(encoding="utf-8"))
        self._docs = {d["id"]: Document(**d) for d in data.get("documents", [])}
        self._chunks = [Chunk(**c) for c in data.get("chunks", [])]

    def _save(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.index_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "documents": [asdict(d) for d in self._docs.values()],
                    "chunks": [asdict(c) for c in self._chunks],
                }
            ),
            encoding="utf-8",
        )
        tmp.replace(self.index_path)

    # ---------- documents ----------
    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex[:12]

    def add_document(self, doc_id: str, name: str, pages: list[str]) -> Document:
        new_chunks = []
        for page_no, text in enumerate(pages, start=1):
            for j, piece in enumerate(chunk_text(text)):
                new_chunks.append(
                    Chunk(id=f"{doc_id}-p{page_no}-{j}", doc_id=doc_id, doc_name=name, page=page_no, text=piece)
                )
        doc = Document(
            id=doc_id,
            name=name,
            pages=len(pages),
            chunk_count=len(new_chunks),
            uploaded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        with self._lock:
            self._docs[doc_id] = doc
            self._chunks.extend(new_chunks)
            self._bm25 = None
            self._save()
        return doc

    def delete_document(self, doc_id: str) -> bool:
        with self._lock:
            if doc_id not in self._docs:
                return False
            del self._docs[doc_id]
            self._chunks = [c for c in self._chunks if c.doc_id != doc_id]
            self._bm25 = None
            self._save()
            return True

    def documents(self) -> list[Document]:
        return sorted(self._docs.values(), key=lambda d: d.uploaded_at)

    def get_document(self, doc_id: str) -> Document | None:
        return self._docs.get(doc_id)

    # ---------- retrieval ----------
    def _index(self) -> tuple[BM25, list[Chunk]]:
        with self._lock:
            if self._bm25 is None:
                self._bm25 = BM25([f"{c.doc_name}\n{c.text}" for c in self._chunks])
            return self._bm25, self._chunks

    def search(self, query: str, k: int, doc_ids: list[str] | None = None) -> list[Chunk]:
        bm25, chunks = self._index()
        hits = bm25.top_k(query, k=len(chunks))
        results = []
        for i, _score in hits:
            c = chunks[i]
            if doc_ids and c.doc_id not in doc_ids:
                continue
            results.append(c)
            if len(results) >= k:
                break
        # Present chunks in reading order (doc, page) - easier for the model to follow
        results.sort(key=lambda c: (c.doc_name, c.page, c.id))
        return results

    def search_with_fallback(self, query: str, k: int, doc_ids: list[str] | None = None, min_hits: int = 3) -> list[Chunk]:
        """Keyword search, topped up with a spread of the materials when it finds little.

        Broad requests ("summarize this lecture", "what are the main points") share few
        words with the notes, so pure keyword search returns nothing useful for them.
        """
        hits = self.search(query, k, doc_ids)
        if len(hits) >= min_hits:
            return hits
        have = {c.id for c in hits}
        extra = self.sample(k - len(hits), doc_ids, exclude=have)
        return sorted(hits + extra, key=lambda c: (c.doc_name, c.page, c.id))

    def sample(self, k: int, doc_ids: list[str] | None = None, exclude: set[str] | None = None) -> list[Chunk]:
        """Spread-out sample of substantial chunks (quizzes with no topic, broad questions)."""
        if k <= 0:
            return []
        exclude = exclude or set()
        pool = [
            c
            for c in self._chunks
            if (not doc_ids or c.doc_id in doc_ids) and c.id not in exclude and len(c.text) > 200
        ] or [c for c in self._chunks if (not doc_ids or c.doc_id in doc_ids) and c.id not in exclude]
        if len(pool) <= k:
            picked = pool
        else:
            step = len(pool) / k
            picked = [pool[int(i * step + random.random() * step)] for i in range(k)]
        return sorted(picked, key=lambda c: (c.doc_name, c.page, c.id))
