import { useState } from "react";
import { Check, CircleAlert, Copy, RotateCcw } from "lucide-react";
import { copyText } from "../clipboard";
import type { ChatMessage } from "../types";
import { Markdown } from "./Markdown";
import { MetaStrip } from "./MetaStrip";

export function MessageBubble({ message, onRetry }: { message: ChatMessage; onRetry: (m: ChatMessage) => void }) {
  const [copied, setCopied] = useState(false);

  if (message.role === "user") {
    const failed = message.status === "failed";
    return (
      <div className="flex flex-col items-end gap-2">
        <div
          data-testid="user-message"
          className={`max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md px-4 py-2.5 text-[15px] ${
            failed ? "border border-fail/60 bg-fail/10" : "bg-raised"
          } ${message.status === "pending" ? "opacity-70" : ""}`}
        >
          {message.content}
        </div>
        {failed && (
          <div data-testid="chat-error" role="alert" className="flex max-w-[85%] items-start gap-2 rounded-lg border border-fail/50 bg-fail/10 px-3 py-2 text-sm text-fail">
            <CircleAlert size={16} className="mt-0.5 shrink-0" aria-hidden />
            <div className="space-y-1.5">
              <p>{message.error}</p>
              <button type="button" onClick={() => onRetry(message)} className="flex items-center gap-1 font-medium underline underline-offset-2">
                <RotateCcw size={13} aria-hidden /> Retry
              </button>
            </div>
          </div>
        )}
      </div>
    );
  }

  const cache = message.metadata?.resolution_source === "LLM_CACHE";
  return (
    <div
      data-testid="assistant-message"
      className={`group relative max-w-[min(100%,46rem)] rounded-2xl rounded-bl-md border border-line bg-surface px-4 py-3 pl-5 before:absolute before:inset-y-3 before:left-0 before:w-[3px] before:rounded-full ${
        cache ? "before:bg-cache" : "before:bg-live"
      }`}
    >
      <button
        type="button"
        aria-label="Copy response"
        onClick={async () => {
          if (await copyText(message.content)) {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }
        }}
        className="absolute right-2 top-2 flex items-center gap-1 rounded-md px-1.5 py-1 text-xs text-muted opacity-0 hover:text-text focus-visible:opacity-100 group-hover:opacity-100"
      >
        {copied ? <Check size={13} aria-hidden /> : <Copy size={13} aria-hidden />}
        {copied ? "Copied" : "Copy"}
      </button>
      <Markdown>{message.content}</Markdown>
      {message.metadata && <MetaStrip metadata={message.metadata} />}
    </div>
  );
}

export function TypingIndicator() {
  return (
    <div data-testid="typing-indicator" className="flex w-fit items-center gap-1.5 rounded-2xl rounded-bl-md border border-line bg-surface px-4 py-3" aria-label="Assistant is thinking">
      {[0, 1, 2].map((i) => (
        <span key={i} className="size-1.5 rounded-full bg-muted motion-safe:animate-pulse" style={{ animationDelay: `${i * 160}ms` }} />
      ))}
    </div>
  );
}
