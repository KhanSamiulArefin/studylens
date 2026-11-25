import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { api, pdfLink, type AskResponse } from "../api";

interface Turn {
  id: number;
  question: string;
  answer?: AskResponse;
  error?: string;
}

const EXAMPLES = [
  "Summarize the key ideas of this lecture",
  "What's the difference between the two main approaches covered?",
  "Explain the hardest concept here with a simple example",
];

/** Turn Claude's cited text segments into one Markdown string with inline [n] citation links. */
function toMarkdown(answer: AskResponse): string {
  return answer.segments
    .map((seg) => {
      if (!seg.cites.length) return seg.text;
      const chips = seg.cites.map((n) => `[${n}](#cite-${n})`).join("");
      // Put the chips before any trailing whitespace/newlines so they stay on the cited line
      return seg.text.replace(/(\s*)$/, `${chips}$1`);
    })
    .join("");
}

function Answer({ turn }: { turn: Turn }) {
  const [active, setActive] = useState<number | null>(null);
  const answer = turn.answer!;
  return (
    <div className="answer">
      <div className="markdown">
        <ReactMarkdown
          remarkPlugins={[remarkGfm, remarkMath]}
          rehypePlugins={[[rehypeKatex, { throwOnError: false }]]}
          components={{
            a({ href, children }) {
              const m = href?.match(/^#cite-(\d+)$/);
              if (m) {
                const n = Number(m[1]);
                return (
                  <button
                    className={`cite ${active === n ? "active" : ""}`}
                    onClick={() => setActive(active === n ? null : n)}
                    title="Show source"
                  >
                    {n}
                  </button>
                );
              }
              return (
                <a href={href} target="_blank" rel="noreferrer">
                  {children}
                </a>
              );
            },
          }}
        >
          {toMarkdown(answer)}
        </ReactMarkdown>
      </div>

      {answer.sources.length > 0 && (
        <div className="sources">
          <h4>Sources</h4>
          <ol>
            {answer.sources.map((s) => (
              <li key={s.n} className={active === s.n ? "active" : ""} onClick={() => setActive(active === s.n ? null : s.n)}>
                <div className="source-head">
                  <span className="cite static">{s.n}</span>
                  <a href={pdfLink(s.doc_id, s.page)} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
                    {s.doc_name} · p. {s.page}
                  </a>
                </div>
                {active === s.n &&
                  s.quotes.map((q, i) => (
                    <blockquote key={i}>
                      “{q.length > 400 ? q.slice(0, 400) + "…" : q}”
                    </blockquote>
                  ))}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

export default function AskView({ hasDocs }: { hasDocs: boolean }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(1);

  useEffect(() => {
    // Braces matter: newer browsers return a Promise from scrollIntoView, which React would treat as a cleanup fn
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, busy]);

  async function ask(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    const id = nextId.current++;
    setTurns((t) => [...t, { id, question: q }]);
    setInput("");
    setBusy(true);
    try {
      const answer = await api.ask(q);
      setTurns((t) => t.map((x) => (x.id === id ? { ...x, answer } : x)));
    } catch (e) {
      setTurns((t) => t.map((x) => (x.id === id ? { ...x, error: (e as Error).message } : x)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="ask">
      <div className="thread">
        {turns.length === 0 && (
          <div className="empty">
            <h1>Ask your course materials</h1>
            <p className="muted">Every answer cites the exact page it came from, so you can check it against your notes.</p>
            {hasDocs ? (
              <div className="examples">
                {EXAMPLES.map((ex) => (
                  <button key={ex} className="chip" onClick={() => ask(ex)}>
                    {ex}
                  </button>
                ))}
              </div>
            ) : (
              <p className="hint">← Start by uploading a lecture PDF.</p>
            )}
          </div>
        )}

        {turns.map((t) => (
          <div key={t.id} className="turn">
            <div className="question">{t.question}</div>
            {t.answer ? (
              <Answer turn={t} />
            ) : t.error ? (
              <div className="error">{t.error}</div>
            ) : (
              <div className="thinking">
                <span className="spinner" aria-hidden="true" /> Searching your materials…
              </div>
            )}
          </div>
        ))}
        <div ref={endRef} />
      </div>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          ask(input);
        }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              ask(input);
            }
          }}
          placeholder={hasDocs ? "Ask a question about your materials…" : "Upload a PDF first"}
          disabled={!hasDocs}
          rows={1}
        />
        <button className="primary" type="submit" disabled={!hasDocs || busy || !input.trim()}>
          Ask
        </button>
      </form>
    </section>
  );
}
