import { isValidElement, useState, type ReactElement, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy } from "lucide-react";
import { copyText } from "../clipboard";

function CodeBlock({ children }: { children?: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const child = Array.isArray(children) ? children[0] : children;
  const props = isValidElement(child) ? (child as ReactElement<{ className?: string; children?: ReactNode }>).props : {};
  const text = String(props.children ?? "").replace(/\n$/, "");
  const lang = /language-([\w-]+)/.exec(props.className ?? "")?.[1];
  return (
    <div className="not-prose overflow-hidden rounded-lg border border-line bg-ink">
      <div className="flex items-center justify-between border-b border-line px-3 py-1.5 text-xs text-muted">
        <span className="num">{lang ?? "text"}</span>
        <button
          type="button"
          onClick={async () => {
            if (await copyText(text)) {
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }
          }}
          className="flex items-center gap-1 rounded px-1.5 py-0.5 hover:text-text"
          aria-label="Copy code"
        >
          {copied ? <Check size={13} /> : <Copy size={13} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto p-3 text-[13px] leading-relaxed"><code className="num">{text}</code></pre>
    </div>
  );
}

export function Markdown({ children }: { children: string }) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
          code: ({ children }) => <code className="inline">{children}</code>,
          a: ({ children, href }) => <a href={href} target="_blank" rel="noreferrer noopener">{children}</a>,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
