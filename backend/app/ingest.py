"""PDF text extraction and chunking.

Each chunk keeps the page it came from, so every answer can cite an exact page.
"""

import re
from pathlib import Path

from pypdf import PdfReader

CHUNK_CHARS = 1500
OVERLAP_CHARS = 200


# Invisible characters some PDF exporters scatter through text (zero-width spaces/joiners, BOM, soft hyphen)
_INVISIBLE = re.compile(r"[​‌‍⁠﻿]")


def normalize(text: str) -> str:
    text = text.replace("\x00", "").replace("­", "")
    text = _INVISIBLE.sub(" ", text)  # a space, not "", in case it was the only separator between words
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pages(path: Path) -> list[str]:
    """Return the text of each page (index 0 = page 1). Empty string for pages with no text."""
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        try:
            pages.append(normalize(page.extract_text() or ""))
        except Exception:  # a single malformed page shouldn't sink the whole upload
            pages.append("")
    return pages


def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    """Split a page into ~size-char chunks on whitespace, with overlap so ideas aren't cut in half."""
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = text.rfind(" ", start + size // 2, end)
            if cut != -1:
                end = cut
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks
