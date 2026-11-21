import type { ChatResponse, Health, StoredMessage } from "./types";

export const API_BASE: string = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** Turn FastAPI's 422 detail list (or a string) into one readable sentence. */
function readableDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((d: { loc?: unknown[]; msg?: string }) => {
      const field = Array.isArray(d.loc) ? String(d.loc[d.loc.length - 1]) : "request";
      return `${field}: ${(d.msg ?? "invalid").replace(/^Value error, /, "")}`;
    });
    return parts.join("; ");
  }
  return "Unexpected error";
}

export function friendlyError(status: number, detail: string): string {
  if (status === 422) return `The backend rejected this message (${detail}). Edit it and send again.`;
  if (status === 503) return "All AI providers are unavailable right now (every API key failed). Nothing was saved, so you can retry.";
  if (status === 502) return "The AI provider rejected this request. Try rewording your message.";
  if (status === 0) return detail;
  return `Request failed (HTTP ${status}): ${detail}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError(0, `Cannot reach the backend at ${API_BASE}. Check that it is running and that it allows this site's origin (CORS).`);
  }
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON body: handled below */
  }
  if (!res.ok) {
    const detail = readableDetail((body as { detail?: unknown } | null)?.detail ?? res.statusText);
    throw new ApiError(res.status, friendlyError(res.status, detail));
  }
  return body as T;
}

export function postChat(
  payload: { session_id: string; message: string; system_prompt?: string },
  simulateFailure?: string,
): Promise<ChatResponse> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (simulateFailure) headers["X-Simulate-Failure"] = simulateFailure;
  return request<ChatResponse>("/chat", { method: "POST", headers, body: JSON.stringify(payload) });
}

export const getHealth = () => request<Health>("/health");

export const getHistory = (sessionId: string) =>
  request<{ session_id: string; messages: StoredMessage[] }>(`/sessions/${encodeURIComponent(sessionId)}/messages`);
