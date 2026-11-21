import { useRef, useState, type KeyboardEvent } from "react";
import { ArrowUp, FlaskConical } from "lucide-react";

interface Props {
  disabled: boolean;
  systemPrompt: string;
  armedFailure: string;
  onSystemPrompt: (v: string) => void;
  onSend: (text: string) => void;
}

export function Composer({ disabled, systemPrompt, armedFailure, onSystemPrompt, onSend }: Props) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const text = value.trim();
    if (!text || disabled) return;
    setValue(""); // the input is empty as soon as the message is sent
    if (ref.current) ref.current.style.height = "auto";
    onSend(text);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="border-t border-line bg-ink px-4 pb-4 pt-3 sm:px-6">
      <div className="mx-auto max-w-3xl space-y-2">
        <label className="flex items-center gap-2 text-xs text-muted">
          <span className="shrink-0">System prompt</span>
          <input
            data-testid="system-prompt-input"
            value={systemPrompt}
            onChange={(e) => onSystemPrompt(e.target.value)}
            maxLength={4000}
            placeholder="Optional. Applies to this session and is sent with each message."
            className="min-w-0 flex-1 rounded-md border border-line bg-surface px-2.5 py-1.5 text-text placeholder:text-muted/70"
          />
        </label>
        <div className="flex items-end gap-2 rounded-2xl border border-line bg-surface p-2 focus-within:border-live/60">
          <textarea
            ref={ref}
            data-testid="chat-input"
            rows={1}
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`;
            }}
            onKeyDown={onKeyDown}
            placeholder="Message the assistant. Enter sends, Shift+Enter adds a line."
            aria-label="Message"
            className="max-h-[200px] min-h-[36px] flex-1 resize-none bg-transparent px-2 py-1.5 text-[15px] outline-none placeholder:text-muted/70"
          />
          <button
            type="button"
            data-testid="send-button"
            onClick={submit}
            disabled={disabled || !value.trim()}
            aria-label="Send message"
            className="grid size-9 shrink-0 place-items-center rounded-xl bg-live text-ink transition-opacity disabled:cursor-not-allowed disabled:opacity-35"
          >
            <ArrowUp size={18} aria-hidden />
          </button>
        </div>
        {armedFailure && (
          <p data-testid="armed-failure" className="num flex items-center gap-1.5 text-xs text-fail">
            <FlaskConical size={13} aria-hidden /> Next message sends X-Simulate-Failure: {armedFailure}
          </p>
        )}
      </div>
    </div>
  );
}
