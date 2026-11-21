import { MessageSquare, Plus, Route, X } from "lucide-react";
import type { Session } from "../types";

interface Props {
  sessions: Session[];
  activeId: string;
  open: boolean;
  onClose: () => void;
  onSelect: (id: string) => void;
  onNew: () => void;
}

export function Sidebar({ sessions, activeId, open, onClose, onSelect, onNew }: Props) {
  return (
    <>
      {open && <div className="fixed inset-0 z-20 bg-black/50 lg:hidden" onClick={onClose} aria-hidden />}
      <aside
        className={`${open ? "fixed inset-y-0 left-0 z-30 flex" : "hidden"} w-64 shrink-0 flex-col border-r border-line bg-surface lg:static lg:z-auto lg:flex`}
        aria-label="Sessions"
      >
        <div className="flex items-center justify-between px-4 py-4">
          <div className="flex items-center gap-2 font-semibold">
            <Route size={18} className="text-live" aria-hidden /> Chat console
          </div>
          <button type="button" onClick={onClose} className="rounded p-1 text-muted hover:text-text lg:hidden" aria-label="Close sessions">
            <X size={18} />
          </button>
        </div>
        <div className="px-3">
          <button
            type="button"
            onClick={() => { onNew(); onClose(); }}
            className="flex w-full items-center gap-2 rounded-lg border border-line bg-raised px-3 py-2 text-left hover:border-live/60"
          >
            <Plus size={16} aria-hidden /> New session
          </button>
        </div>
        <nav className="mt-3 flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
          {sessions.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => { onSelect(s.id); onClose(); }}
              aria-current={s.id === activeId ? "true" : undefined}
              className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left ${s.id === activeId ? "bg-raised text-text" : "text-muted hover:bg-raised/60 hover:text-text"}`}
            >
              <MessageSquare size={14} className="shrink-0" aria-hidden />
              <span className="truncate">{s.title}</span>
            </button>
          ))}
        </nav>
        <p className="border-t border-line px-4 py-3 text-xs text-muted">Each page load starts a new session. Sessions here live in this tab; the backend keeps the stored history.</p>
      </aside>
    </>
  );
}
