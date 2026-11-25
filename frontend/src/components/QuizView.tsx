import { useState } from "react";
import { api, pdfLink, type Difficulty, type QuizQuestion } from "../api";
import InlineMarkdown from "./InlineMarkdown";

function QuestionCard({
  q,
  index,
  picked,
  onPick,
}: {
  q: QuizQuestion;
  index: number;
  picked: number | undefined;
  onPick: (i: number) => void;
}) {
  const answered = picked !== undefined;
  return (
    <div className="qcard">
      <p className="qtext">
        <span className="qnum">{index + 1}</span>
        <span>
          <InlineMarkdown text={q.question} />
        </span>
      </p>
      <div className="options">
        {q.options.map((opt, i) => {
          let cls = "option";
          if (answered && i === q.answer_index) cls += " correct";
          else if (answered && i === picked) cls += " wrong";
          return (
            <button key={i} className={cls} disabled={answered} onClick={() => onPick(i)}>
              <span className="letter">{String.fromCharCode(65 + i)}</span>
              <span>
                <InlineMarkdown text={opt} />
              </span>
            </button>
          );
        })}
      </div>
      {answered && (
        <div className={`feedback ${picked === q.answer_index ? "good" : "bad"}`}>
          <strong>{picked === q.answer_index ? "Correct." : "Not quite."}</strong> <InlineMarkdown text={q.explanation} />
          {q.source && (
            <a href={pdfLink(q.source.doc_id, q.source.page)} target="_blank" rel="noreferrer" className="source-link">
              Review: {q.source.doc_name} · p. {q.source.page}
            </a>
          )}
        </div>
      )}
    </div>
  );
}

export default function QuizView({ hasDocs }: { hasDocs: boolean }) {
  const [topic, setTopic] = useState("");
  const [count, setCount] = useState(5);
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [questions, setQuestions] = useState<QuizQuestion[]>([]);
  const [picks, setPicks] = useState<Record<number, number>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function generate() {
    setBusy(true);
    setError("");
    try {
      const res = await api.quiz(topic, count, difficulty);
      setQuestions(res.questions);
      setPicks({});
      if (!res.questions.length) setError("Claude didn't return any usable questions. Try again or pick a topic.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const answered = Object.keys(picks).length;
  const correct = questions.filter((q, i) => picks[i] === q.answer_index).length;
  const done = questions.length > 0 && answered === questions.length;

  return (
    <section className="quiz">
      <div className="quiz-form">
        <h1>Quiz yourself</h1>
        <p className="muted">Questions are written from your materials, and each one links back to the page it tests.</p>
        <div className="form-row">
          <label className="grow">
            Topic <span className="muted">(optional)</span>
            <input
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g. dynamic programming, mitosis, supply and demand"
              onKeyDown={(e) => e.key === "Enter" && hasDocs && !busy && generate()}
            />
          </label>
          <label>
            Questions
            <select value={count} onChange={(e) => setCount(Number(e.target.value))}>
              {[3, 5, 10].map((n) => (
                <option key={n}>{n}</option>
              ))}
            </select>
          </label>
          <label>
            Difficulty
            <select value={difficulty} onChange={(e) => setDifficulty(e.target.value as Difficulty)}>
              <option value="easy">Easy</option>
              <option value="medium">Medium</option>
              <option value="hard">Hard</option>
            </select>
          </label>
          <button className="primary" onClick={generate} disabled={!hasDocs || busy}>
            {busy ? "Writing…" : questions.length ? "New quiz" : "Generate"}
          </button>
        </div>
        {!hasDocs && <p className="hint">← Upload a PDF first.</p>}
        {error && <p className="error">{error}</p>}
      </div>

      {busy && (
        <div className="thinking">
          <span className="spinner" aria-hidden="true" /> Writing questions from your materials…
        </div>
      )}

      {!busy && questions.length > 0 && (
        <>
          <div className={`score ${done ? "done" : ""}`}>
            {done ? `You got ${correct} of ${questions.length} right.` : `${answered} of ${questions.length} answered · ${correct} correct`}
          </div>
          {questions.map((q, i) => (
            <QuestionCard key={i} q={q} index={i} picked={picks[i]} onPick={(opt) => setPicks((p) => ({ ...p, [i]: opt }))} />
          ))}
        </>
      )}
    </section>
  );
}
