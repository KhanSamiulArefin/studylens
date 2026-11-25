import { useRef, useState } from "react";
import { api, type DocumentInfo } from "../api";

interface Props {
  docs: DocumentInfo[];
  onChange: () => void;
}

export default function Library({ docs, onChange }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState<string[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [dragging, setDragging] = useState(false);
  // Inline confirm instead of window.confirm(), which embedded browsers often block (it then returns false)
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<string | null>(null);

  async function handleFiles(files: FileList | File[]) {
    const pdfs = Array.from(files);
    if (!pdfs.length) return;
    setErrors([]);
    setUploading(pdfs.map((f) => f.name));
    const failed: string[] = [];
    for (const file of pdfs) {
      try {
        await api.upload(file);
      } catch (e) {
        failed.push(`${file.name}: ${(e as Error).message}`);
      }
      setUploading((u) => u.filter((n) => n !== file.name));
    }
    setErrors(failed);
    onChange();
  }

  async function remove(doc: DocumentInfo) {
    setRemovingId(doc.id);
    setErrors([]);
    try {
      await api.deleteDocument(doc.id);
    } catch (e) {
      setErrors([`Couldn't remove ${doc.name}: ${(e as Error).message}`]);
    } finally {
      setRemovingId(null);
      setConfirmingId(null);
      onChange();
    }
  }

  return (
    <aside className="library">
      <h2>Your materials</h2>
      <div
        className={`dropzone ${dragging ? "dragging" : ""}`}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
        role="button"
        tabIndex={0}
      >
        <strong>Drop PDFs here</strong>
        <span>or click to browse: lecture slides, notes, readings</span>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          hidden
          onChange={(e) => {
            if (e.target.files) handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {errors.map((err) => (
        <p key={err} className="error small">
          {err}
        </p>
      ))}

      <ul className="doc-list">
        {uploading.map((name) => (
          <li key={`up-${name}`} className="doc uploading">
            <span className="spinner" aria-hidden="true" />
            <div className="doc-meta">
              <span className="doc-name">{name}</span>
              <span className="doc-sub">Reading and indexing…</span>
            </div>
          </li>
        ))}
        {docs.map((d) => {
          const confirming = confirmingId === d.id;
          const removing = removingId === d.id;
          return (
            <li key={d.id} className={`doc ${confirming ? "confirming" : ""}`}>
              <span className="doc-icon" aria-hidden="true">
                PDF
              </span>
              <div className="doc-meta">
                <a className="doc-name" href={`/api/documents/${d.id}/file`} target="_blank" rel="noreferrer" title={d.name}>
                  {d.name}
                </a>
                {confirming ? (
                  <span className="doc-confirm">
                    <span>Remove this file?</span>
                    <button className="danger-btn" onClick={() => remove(d)} disabled={removing} autoFocus>
                      {removing ? "Removing…" : "Remove"}
                    </button>
                    <button className="text-btn" onClick={() => setConfirmingId(null)} disabled={removing}>
                      Cancel
                    </button>
                  </span>
                ) : (
                  <span className="doc-sub">
                    {d.pages} pages · {d.chunk_count} passages
                  </span>
                )}
              </div>
              {!confirming && (
                <button
                  className="icon-btn"
                  onClick={() => setConfirmingId(d.id)}
                  aria-label={`Remove ${d.name}`}
                  title="Remove"
                >
                  ×
                </button>
              )}
            </li>
          );
        })}
      </ul>
      {!docs.length && !uploading.length && <p className="muted small">Nothing here yet. Upload a PDF to get started.</p>}
    </aside>
  );
}
