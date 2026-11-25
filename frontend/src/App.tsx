import { useCallback, useEffect, useState } from "react";
import { api, type DocumentInfo, type Health } from "./api";
import Library from "./components/Library";
import AskView from "./components/AskView";
import QuizView from "./components/QuizView";

type Tab = "ask" | "quiz";

export default function App() {
  const [tab, setTab] = useState<Tab>("ask");
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [backendDown, setBackendDown] = useState(false);

  const refreshDocs = useCallback(async () => {
    try {
      setDocs(await api.listDocuments());
      setBackendDown(false);
    } catch {
      setBackendDown(true);
    }
  }, []);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setBackendDown(true));
    refreshDocs();
  }, [refreshDocs]);

  const hasDocs = docs.length > 0;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden="true">
            <circle cx="14" cy="14" r="9" fill="none" stroke="currentColor" strokeWidth="4" />
            <path d="M21 21l7 7" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
          </svg>
          <span>StudyLens</span>
        </div>
        <nav className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === "ask"} className={tab === "ask" ? "active" : ""} onClick={() => setTab("ask")}>
            Ask
          </button>
          <button role="tab" aria-selected={tab === "quiz"} className={tab === "quiz" ? "active" : ""} onClick={() => setTab("quiz")}>
            Quiz me
          </button>
        </nav>
        <div className="status">
          {backendDown ? (
            <span className="pill pill-bad">Backend offline</span>
          ) : health && !health.api_key_configured ? (
            <span className="pill pill-warn" title={`Add ${health.key_env} to backend/.env and restart the server`}>
              No API key
            </span>
          ) : health ? (
            <span className="pill pill-ok" title={`Provider: ${health.provider}`}>
              {health.model}
            </span>
          ) : null}
        </div>
      </header>

      <div className="layout">
        <Library docs={docs} onChange={refreshDocs} />
        <main className="main">
          {backendDown && (
            <div className="banner banner-bad">
              Can't reach the backend. Start it with <code>uvicorn app.main:app --reload</code> in the <code>backend</code> folder.
            </div>
          )}
          {/* Keep both views mounted so switching tabs doesn't lose the conversation or quiz */}
          <div hidden={tab !== "ask"}>
            <AskView hasDocs={hasDocs} />
          </div>
          <div hidden={tab !== "quiz"}>
            <QuizView hasDocs={hasDocs} />
          </div>
        </main>
      </div>
    </div>
  );
}
