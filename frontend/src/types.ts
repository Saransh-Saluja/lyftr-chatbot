export type ResolutionSource = "LIVE_INFERENCE" | "LLM_CACHE";

export interface Metadata {
  resolution_source: ResolutionSource;
  model: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  key_id: string | null;
  fallback_attempts: number;
}

export interface ChatResponse {
  session_id: string;
  reply: string;
  metadata: Metadata;
}

export interface Health {
  status: string;
  keys_configured: number;
  cache_enabled: boolean;
  failure_simulation?: boolean;
}

export interface StoredMessage {
  role: "user" | "assistant";
  content: string;
  created_at?: string;
  metadata?: Partial<Metadata>;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  metadata?: Metadata;
  /** user messages only: pending while in flight, failed if the request was rejected */
  status?: "pending" | "sent" | "failed";
  error?: string;
}

export interface Session {
  id: string;
  title: string;
  messages: ChatMessage[];
  systemPrompt: string;
}

/** One real request, shown in the diagnostics panel. Never synthesised. */
export interface RequestLog {
  id: string;
  at: number;
  sessionId: string;
  ok: boolean;
  status?: number;
  metadata?: Metadata;
  simulated?: string;
}
