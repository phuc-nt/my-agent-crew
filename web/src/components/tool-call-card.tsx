import { useState } from "react";
import { vi } from "../i18n/vi";
import { delegateAgent, delegateTask, parseDelegateResult } from "../lib/delegate-result";
import type { ThreadItem, ToolStatus } from "../state/thread-reducer";

type ToolItem = Extract<ThreadItem, { kind: "tool" }>;

const DELEGATE = "delegate";

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

interface Props {
  item: ToolItem;
  /** Names the agent ids the crew knows, so a card can show a name instead of an id. */
  agentName?: (id: string) => string;
  /** Opens the child conversation this call created; absent means the button is hidden. */
  onOpenConversation?: (conversationId: string) => void;
}

export function ToolCallCard({ item, agentName, onOpenConversation }: Props) {
  const [open, setOpen] = useState(false);
  const hasOutput = item.output !== null && item.output !== "";
  if (item.name === DELEGATE) {
    return (
      <DelegateCard
        item={item}
        agentName={agentName}
        onOpenConversation={onOpenConversation}
        open={open}
        setOpen={setOpen}
      />
    );
  }
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

/**
 * A handed-off task, shown as the job rather than as a tool call: who took it, what they
 * were asked, and — once they answer — how it went and what it cost. The child runs as
 * its own conversation, so the card offers a way in rather than inlining the whole thing.
 */
function DelegateCard({
  item,
  agentName,
  onOpenConversation,
  open,
  setOpen,
}: Props & { open: boolean; setOpen: (fn: (o: boolean) => boolean) => void }) {
  const target = delegateAgent(item.arguments);
  const task = delegateTask(item.arguments);
  const result = item.output ? parseDelegateResult(item.output) : null;
  const name = target ? (agentName?.(target) ?? target) : vi.delegateUnknownAgent;
  return (
    <div className="tool-card delegate-card" data-testid="delegate-card" data-tool={DELEGATE}>
      <div className="tool-header">
        <span className="tool-name">🤝 {vi.delegateTo.replace("{agent}", name)}</span>
        <span className={`tool-status ${item.status}`}>
          {item.status === "running" ? vi.delegateRunning : STATUS_LABEL[item.status]}
        </span>
      </div>
      <div className="tool-arguments" title={vi.delegateTask}>
        {task || "—"}
      </div>
      {result && (
        <div className="delegate-result">
          <span className="delegate-chip" data-testid="delegate-status">
            {result.status}
          </span>
          <span className="muted">
            ${result.spentUsd.toFixed(4)} · {vi.delegateSteps.replace("{n}", String(result.steps))}
          </span>
          {onOpenConversation && (
            <button
              type="button"
              className="link-button"
              onClick={() => onOpenConversation(result.conversationId)}
            >
              {vi.delegateOpenChild}
            </button>
          )}
        </div>
      )}
      {item.output && (
        <>
          <button type="button" className="link-button" onClick={() => setOpen((o) => !o)}>
            {open ? vi.hideOutput : vi.showOutput}
          </button>
          {open && <pre className="tool-output">{result ? result.reply : item.output}</pre>}
        </>
      )}
    </div>
  );
}
