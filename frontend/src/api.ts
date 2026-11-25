export interface DocumentInfo {
  id: string;
  name: string;
  pages: number;
  chunk_count: number;
  uploaded_at: string;
}

export interface Health {
  ok: boolean;
  provider: "claude" | "gemini";
  model: string;
  api_key_configured: boolean;
  key_env: string;
}

export interface Source {
  n: number;
  doc_id: string;
  doc_name: string;
  page: number;
  quotes: string[];
}

export interface AskResponse {
  segments: { text: string; cites: number[] }[];
  sources: Source[];
  retrieved: { doc_name: string; page: number }[];
}

export interface QuizQuestion {
  question: string;
  options: string[];
  answer_index: number;
  explanation: string;
  source: { doc_id: string; doc_name: string; page: number } | null;
}

export type Difficulty = "easy" | "medium" | "hard";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      /* non-JSON error body */
    }
    throw new Error(message);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request<Health>("/api/health"),
  listDocuments: () => request<DocumentInfo[]>("/api/documents"),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentInfo>("/api/documents", { method: "POST", body: form });
  },
  deleteDocument: (id: string) => request<void>(`/api/documents/${id}`, { method: "DELETE" }),
  ask: (question: string) => request<AskResponse>("/api/ask", json({ question })),
  quiz: (topic: string, num_questions: number, difficulty: Difficulty) =>
    request<{ questions: QuizQuestion[] }>("/api/quiz", json({ topic, num_questions, difficulty })),
};

export const pdfLink = (docId: string, page: number) => `/api/documents/${docId}/file#page=${page}`;
