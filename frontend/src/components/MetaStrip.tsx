import { Database, KeyRound, Zap } from "lucide-react";
import type { Metadata } from "../types";

/** Failed keys are always the ones BEFORE the answering key (the backend tries keys in order),
 *  so this trace is derived purely from real response metadata - nothing is invented. */
function RouteTrace({ m }: { m: Metadata }) {
  if (m.resolution_source === "LLM_CACHE") {
    return (
      <span className="flex items-center gap-1.5 text-cache" title="Served from the response cache; no provider was called">
        <Database size={13} aria-hidden /> cache <span className="text-muted">· no provider call</span>
      </span>
    );
  }
  const answering = m.key_id ?? "?";
  const n = Number(/(\d+)$/.exec(answering)?.[1] ?? NaN);
  const failed = Number.isFinite(n) && n - 1 === m.fallback_attempts ? Array.from({ length: m.fallback_attempts }, (_, i) => `key_${i + 1}`) : [];
  return (
    <span className="num flex flex-wrap items-center gap-1.5" data-testid="route-trace">
      {failed.map((k) => (
        <span key={k} className="flex items-center gap-1.5 text-fail">
          <KeyRound size={12} aria-hidden /> {k} <span aria-label="failed">✕</span>
          <span className="text-muted">→</span>
        </span>
      ))}
      {failed.length === 0 && m.fallback_attempts > 0 && <span className="text-fail">{m.fallback_attempts} failed →</span>}
      <span className="flex items-center gap-1.5 text-live">
        <KeyRound size={12} aria-hidden /> {answering} <span aria-label="answered">✓</span>
      </span>
    </span>
  );
}

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <dt className="text-muted">{label}</dt>
      <dd className="num">{children}</dd>
    </div>
  );
}

export function MetaStrip({ metadata: m }: { metadata: Metadata }) {
  const cache = m.resolution_source === "LLM_CACHE";
  return (
    <div className="mt-3 space-y-2 border-t border-line pt-3 text-xs">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
        <span
          data-testid="meta-source"
          className={`num inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 font-medium ${
            cache ? "bg-cache/15 text-cache" : "bg-live/15 text-live"
          }`}
        >
          {cache ? <Database size={12} aria-hidden /> : <Zap size={12} aria-hidden />}
          {m.resolution_source}
        </span>
        <RouteTrace m={m} />
      </div>
      <dl className="flex flex-wrap gap-x-5 gap-y-1">
        <Item label="Model"><span data-testid="meta-model">{m.model}</span></Item>
        <Item label="Latency"><span data-testid="meta-latency">{m.latency_ms} ms</span></Item>
        <Item label="Input tokens"><span data-testid="meta-input-tokens">{m.input_tokens}</span></Item>
        <Item label="Output tokens"><span data-testid="meta-output-tokens">{m.output_tokens}</span></Item>
        <Item label="Key"><span data-testid="meta-key-id">{m.key_id ?? "null"}</span></Item>
        <Item label="Fallback attempts"><span data-testid="meta-fallback-attempts">{m.fallback_attempts}</span></Item>
      </dl>
    </div>
  );
}
