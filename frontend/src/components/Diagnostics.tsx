import { useState } from "react";
import { Activity, Check, Copy, FlaskConical, RefreshCw, X } from "lucide-react";
import { API_BASE, getHistory } from "../api";
import { copyText } from "../clipboard";
import type { Health, RequestLog } from "../types";

const PRESETS = ["key_1=429", "key_1=500", "key_1=429,key_2=500", "*=429"];

interface Props {
  open: boolean;
  onClose: () => void;
  health: Health | null;
  healthError: string | null;
  checking: boolean;
  onRefresh: () => void;
  sessionId: string;
  log: RequestLog[];
  armedFailure: string;
  onArm: (v: string) => void;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1">
      <dt className="text-muted">{label}</dt>
      <dd className="num truncate text-right">{children}</dd>
    </div>
  );
}

export function Diagnostics(p: Props) {
  const [stored, setStored] = useState<string | null>(null);
  const [storedError, setStoredError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [custom, setCustom] = useState("");
  const simOn = p.health?.failure_simulation === true;

  const loadStored = async () => {
    setStoredError(null);
    try {
      setStored(JSON.stringify(await getHistory(p.sessionId), null, 2));
    } catch (e) {
      setStored(null);
      setStoredError(e instanceof Error ? e.message : "failed");
    }
  };

  return (
    <>
      {p.open && <div className="fixed inset-0 z-20 bg-black/50 xl:hidden" onClick={p.onClose} aria-hidden />}
      <aside
        data-testid="diagnostics-panel"
        aria-label="Diagnostics"
        className={`${p.open ? "fixed inset-y-0 right-0 z-30 flex" : "hidden"} w-80 shrink-0 flex-col overflow-y-auto border-l border-line bg-surface xl:static xl:z-auto xl:flex`}
      >
        <div className="flex items-center justify-between px-4 py-4">
          <h2 className="flex items-center gap-2 font-semibold"><Activity size={16} className="text-live" aria-hidden /> Diagnostics</h2>
          <button type="button" onClick={p.onClose} className="rounded p-1 text-muted hover:text-text xl:hidden" aria-label="Close diagnostics"><X size={18} /></button>
        </div>

        <section className="border-t border-line px-4 py-3">
          <div className="mb-1 flex items-center justify-between">
            <h3 className="font-medium">Backend</h3>
            <button type="button" onClick={p.onRefresh} className="flex items-center gap-1 text-xs text-muted hover:text-text" aria-label="Refresh health">
              <RefreshCw size={12} className={p.checking ? "motion-safe:animate-spin" : ""} aria-hidden /> Check
            </button>
          </div>
          <dl data-testid="health-info" className="text-[13px]">
            <Row label="Status">
              <span className={p.health ? "text-ok" : "text-fail"}>{p.health ? "ok" : "unreachable"}</span>
            </Row>
            {p.health ? (
              <>
                <Row label="Keys configured">{p.health.keys_configured}</Row>
                <Row label="Cache">{p.health.cache_enabled ? "enabled" : "disabled"}</Row>
                <Row label="Failure simulation">{simOn ? "enabled" : "disabled"}</Row>
              </>
            ) : (
              <p className="py-1 text-xs text-fail">{p.healthError}</p>
            )}
            <Row label="API">{API_BASE}</Row>
          </dl>
        </section>

        <section className="border-t border-line px-4 py-3">
          <h3 className="mb-1 font-medium">Session</h3>
          <div className="flex items-center gap-2">
            <code data-testid="session-id" className="num min-w-0 flex-1 truncate text-xs text-muted" title={p.sessionId}>{p.sessionId}</code>
            <button
              type="button"
              aria-label="Copy session id"
              onClick={async () => { if (await copyText(p.sessionId)) { setCopied(true); setTimeout(() => setCopied(false), 1500); } }}
              className="text-muted hover:text-text"
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </button>
          </div>
          <button type="button" onClick={loadStored} className="mt-2 text-xs text-live underline underline-offset-2">View stored history (GET /sessions/…)</button>
          {storedError && <p className="mt-1 text-xs text-fail">{storedError}</p>}
          {stored && <pre className="num mt-2 max-h-56 overflow-auto rounded-lg border border-line bg-ink p-2 text-[11px]">{stored}</pre>}
        </section>

        <section className="border-t border-line px-4 py-3">
          <h3 className="mb-1 flex items-center gap-1.5 font-medium"><FlaskConical size={14} aria-hidden /> Failover test</h3>
          {simOn ? (
            <>
              <p className="mb-2 text-xs text-muted">Make chosen keys fail for the next message only.</p>
              <div className="flex flex-wrap gap-1.5">
                {PRESETS.map((v) => (
                  <button
                    key={v}
                    type="button"
                    aria-pressed={p.armedFailure === v}
                    onClick={() => p.onArm(p.armedFailure === v ? "" : v)}
                    className={`num rounded-md border px-2 py-1 text-xs ${p.armedFailure === v ? "border-fail bg-fail/15 text-fail" : "border-line text-muted hover:text-text"}`}
                  >
                    {v}
                  </button>
                ))}
              </div>
              <form className="mt-2 flex gap-1.5" onSubmit={(e) => { e.preventDefault(); p.onArm(custom.trim()); }}>
                <input value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="key_2=503" aria-label="Custom failure header" className="num min-w-0 flex-1 rounded-md border border-line bg-ink px-2 py-1 text-xs" />
                <button type="submit" className="rounded-md border border-line px-2 text-xs text-muted hover:text-text">Arm</button>
              </form>
            </>
          ) : (
            <p className="text-xs text-muted">{p.health ? "Disabled on this server (ENABLE_FAILURE_SIMULATION is not true)." : "Unavailable until the backend is reachable."}</p>
          )}
        </section>

        <section className="border-t border-line px-4 py-3">
          <h3 className="mb-1 font-medium">Recent requests</h3>
          {p.log.length === 0 ? (
            <p className="text-xs text-muted">Requests you send in this tab appear here.</p>
          ) : (
            <ul data-testid="request-log" className="space-y-1.5 text-xs">
              {p.log.map((r) => (
                <li key={r.id} className="num flex items-center justify-between gap-2 rounded-md bg-ink px-2 py-1.5">
                  <span className="text-muted">{new Date(r.at).toLocaleTimeString([], { hour12: false })}</span>
                  {r.ok && r.metadata ? (
                    <>
                      <span className={r.metadata.resolution_source === "LLM_CACHE" ? "text-cache" : "text-live"}>{r.metadata.resolution_source === "LLM_CACHE" ? "cache" : r.metadata.key_id}</span>
                      <span className={r.metadata.fallback_attempts ? "text-fail" : "text-muted"}>fb {r.metadata.fallback_attempts}</span>
                      <span>{r.metadata.latency_ms} ms</span>
                    </>
                  ) : (
                    <span className="flex-1 text-right text-fail">{r.status ? `HTTP ${r.status}` : "network error"}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      </aside>
    </>
  );
}
