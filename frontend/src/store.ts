import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, getHealth, postChat } from "./api";
import type { ChatMessage, Health, RequestLog, Session } from "./types";

export function uid(prefix: string): string {
  const c = globalThis.crypto;
  const raw = c && "randomUUID" in c ? c.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36);
  return `${prefix}-${raw}`;
}

const newSession = (n: number): Session => ({ id: uid("s"), title: `Session ${n}`, messages: [], systemPrompt: "" });

export function useHealth(intervalMs = 20000) {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const refresh = useCallback(async () => {
    setChecking(true);
    try {
      setHealth(await getHealth());
      setError(null);
    } catch (e) {
      setHealth(null);
      setError(e instanceof Error ? e.message : "unreachable");
    } finally {
      setChecking(false);
    }
  }, []);
  useEffect(() => {
    void refresh();
    const t = setInterval(() => void refresh(), intervalMs);
    return () => clearInterval(t);
  }, [refresh, intervalMs]);
  return { health, error, checking, refresh };
}

export function useChatStore() {
  // A brand-new session id is generated on every page load (contract requirement).
  const [sessions, setSessions] = useState<Session[]>(() => [newSession(1)]);
  const [activeId, setActiveId] = useState<string>(() => sessions[0]?.id ?? "");
  const [sendingIds, setSendingIds] = useState<string[]>([]);
  const [log, setLog] = useState<RequestLog[]>([]);
  const [armedFailure, setArmedFailure] = useState<string>("");
  const counter = useRef(1);

  const active = sessions.find((s) => s.id === activeId) ?? sessions[0];

  const patchSession = (id: string, fn: (s: Session) => Session) =>
    setSessions((all) => all.map((s) => (s.id === id ? fn(s) : s)));

  const createSession = useCallback(() => {
    counter.current += 1;
    const s = newSession(counter.current);
    setSessions((all) => [s, ...all]);
    setActiveId(s.id);
  }, []);

  const setSystemPrompt = (value: string) => active && patchSession(active.id, (s) => ({ ...s, systemPrompt: value }));

  const send = useCallback(
    async (text: string, retryOfId?: string) => {
      if (!active) return;
      const sid = active.id;
      const prompt = active.systemPrompt.trim();
      const simulate = armedFailure.trim() || undefined;
      const userId = retryOfId ?? uid("m");
      patchSession(sid, (s) => ({
        ...s,
        title: s.messages.length === 0 ? text.slice(0, 40) : s.title,
        messages: retryOfId
          ? s.messages.map((m) => (m.id === retryOfId ? { ...m, status: "pending", error: undefined } : m))
          : [...s.messages, { id: userId, role: "user", content: text, status: "pending" }],
      }));
      setSendingIds((ids) => [...ids, sid]);
      if (simulate) setArmedFailure(""); // the hook is one-shot: it applies to this request only
      try {
        const res = await postChat({ session_id: sid, message: text, ...(prompt ? { system_prompt: prompt } : {}) }, simulate);
        const reply: ChatMessage = { id: uid("m"), role: "assistant", content: res.reply, metadata: res.metadata };
        patchSession(sid, (s) => ({
          ...s,
          messages: [...s.messages.map((m) => (m.id === userId ? { ...m, status: "sent" as const } : m)), reply],
        }));
        setLog((l) => [{ id: uid("r"), at: Date.now(), sessionId: sid, ok: true, metadata: res.metadata, simulated: simulate }, ...l].slice(0, 20));
      } catch (e) {
        const err = e instanceof ApiError ? e : new ApiError(0, "Unexpected error");
        patchSession(sid, (s) => ({
          ...s,
          messages: s.messages.map((m) => (m.id === userId ? { ...m, status: "failed" as const, error: err.message } : m)),
        }));
        setLog((l) => [{ id: uid("r"), at: Date.now(), sessionId: sid, ok: false, status: err.status, simulated: simulate }, ...l].slice(0, 20));
      } finally {
        setSendingIds((ids) => ids.filter((i) => i !== sid));
      }
    },
    [active, armedFailure],
  );

  return {
    sessions, active, activeId: active?.id ?? "", setActiveId, createSession, send, setSystemPrompt,
    sending: active ? sendingIds.includes(active.id) : false,
    log, armedFailure, setArmedFailure,
  };
}
