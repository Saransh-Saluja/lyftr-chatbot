import { useEffect, useRef, useState } from "react";
import { Activity, Menu } from "lucide-react";
import { Composer } from "./components/Composer";
import { Diagnostics } from "./components/Diagnostics";
import { MessageBubble, TypingIndicator } from "./components/MessageBubble";
import { Sidebar } from "./components/Sidebar";
import { useChatStore, useHealth } from "./store";

const SUGGESTIONS = [
  "What is the capital of France?",
  "Explain HTTP 429 in one sentence.",
  "Write a Python function that reverses a string.",
];

export default function App() {
  const store = useChatStore();
  const { health, error, checking, refresh } = useHealth();
  const [drawer, setDrawer] = useState<"sessions" | "diagnostics" | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const messages = store.active?.messages ?? [];

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [messages.length, store.sending, store.activeId]);

  return (
    <div className="flex h-full">
      <Sidebar
        sessions={store.sessions}
        activeId={store.activeId}
        open={drawer === "sessions"}
        onClose={() => setDrawer(null)}
        onSelect={store.setActiveId}
        onNew={store.createSession}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <button type="button" onClick={() => setDrawer("sessions")} className="rounded p-1 text-muted hover:text-text lg:hidden" aria-label="Open sessions"><Menu size={20} /></button>
            <h1 className="truncate font-semibold">{store.active?.title}</h1>
          </div>
          <div className="flex items-center gap-3 text-xs text-muted">
            <span className="flex items-center gap-1.5">
              <span className={`size-2 rounded-full ${health ? "bg-ok" : "bg-fail"}`} aria-hidden />
              {health ? `Backend ok · ${health.keys_configured} keys` : "Backend unreachable"}
            </span>
            <button type="button" onClick={() => setDrawer("diagnostics")} className="rounded p-1 hover:text-text xl:hidden" aria-label="Open diagnostics"><Activity size={18} /></button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6" data-testid="message-list">
          <div className="mx-auto flex max-w-3xl flex-col gap-5">
            {messages.length === 0 && (
              <div className="py-16 text-center">
                <h2 className="text-xl font-semibold">Start a conversation</h2>
                <p className="mx-auto mt-2 max-w-md text-muted">
                  Every reply shows how it was produced: from the cache or a live model call, which key answered, and its token use.
                  Send the same first message in a new session to see a cache hit.
                </p>
                <div className="mt-6 flex flex-col items-center gap-2">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} type="button" onClick={() => void store.send(s)} className="rounded-lg border border-line bg-surface px-4 py-2 text-left text-muted hover:border-live/60 hover:text-text">
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} onRetry={(msg) => void store.send(msg.content, msg.id)} />
            ))}
            {store.sending && <TypingIndicator />}
            <div ref={endRef} />
          </div>
        </div>

        <Composer
          disabled={store.sending}
          systemPrompt={store.active?.systemPrompt ?? ""}
          armedFailure={store.armedFailure}
          onSystemPrompt={store.setSystemPrompt}
          onSend={(t) => void store.send(t)}
        />
      </main>

      <Diagnostics
        open={drawer === "diagnostics"}
        onClose={() => setDrawer(null)}
        health={health}
        healthError={error}
        checking={checking}
        onRefresh={() => void refresh()}
        sessionId={store.activeId}
        log={store.log}
        armedFailure={store.armedFailure}
        onArm={store.setArmedFailure}
      />
    </div>
  );
}
