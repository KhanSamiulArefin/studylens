"""Re-read every uploaded PDF and rebuild its passages, keeping document ids.

Run after changing how PDFs are parsed or chunked (stop the server first):
    python -m app.reindex
"""

from .config import INDEX_PATH, UPLOAD_DIR
from .ingest import extract_pages
from .store import Store


def main() -> None:
    store = Store(INDEX_PATH)
    docs = store.documents()
    if not docs:
        print("No documents to reindex.")
        return
    for doc in docs:
        path = UPLOAD_DIR / f"{doc.id}.pdf"
        if not path.exists():
            print(f"skip  {doc.name}: file missing")
            continue
        pages = extract_pages(path)
        store.delete_document(doc.id)
        new = store.add_document(doc.id, doc.name, pages)
        print(f"ok    {doc.name}: {doc.chunk_count} -> {new.chunk_count} passages")


if __name__ == "__main__":
    main()
