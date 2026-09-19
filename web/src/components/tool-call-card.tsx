import { useState } from "react";
import { vi } from "../i18n/vi";
import type { ThreadItem, ToolStatus } from "../state/thread-reducer";

type ToolItem = Extract<ThreadItem, { kind: "tool" }>;

const STATUS_LABEL: Record<ToolStatus, string> = {
  running: vi.toolRunning,
  done: vi.toolDone,
  failed: vi.toolFailed,
  awaiting: vi.toolAwaiting,
  denied: vi.toolDenied,
};

export function summarizeArguments(args: Record<string, unknown>): string {
  const parts = Object.entries(args).map(([key, value]) => {
    const text = typeof value === "string" ? value : JSON.stringify(value);
    return `${key}=${text.length > 60 ? `${text.slice(0, 57)}…` : text}`;
  });
  return parts.join(", ");
}

export function ToolCallCard({ item }: { item: ToolItem }) {
  const [open, setOpen] = useState(false);
  const hasOutput = item.output !== null && item.output !== "";
  return (
    <div className={`tool-card ${item.status}`} data-testid="tool-card" data-tool={item.name}>
      <div className="tool-header">
        <span className="tool-name">🔧 {item.name}</span>
        <span className={`tool-status ${item.status}`}>{STATUS_LABEL[item.status]}</span>
      </div>
      <div className="tool-arguments" title={vi.arguments}>
        {summarizeArguments(item.arguments) || "—"}
      </div>
      {hasOutput && (
        <>
          <button type="button" className="link-button" onClick={() => setOpen((o) => !o)}>
            {open ? vi.hideOutput : vi.showOutput}
          </button>
          {open && <pre className="tool-output">{item.output}</pre>}
        </>
      )}
    </div>
  );
}
