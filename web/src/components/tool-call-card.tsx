import { useState } from "react";
import { vi } from "../i18n/vi";
import { delegateAgent, delegateTask, parseDelegateResult } from "../lib/delegate-result";
import type { ThreadItem, ToolStatus } from "../state/thread-reducer";
import { AgentAvatar } from "./ui/agent-avatar";
import { Icon, type IconName } from "./ui/icon";

type ToolItem = Extract<ThreadItem, { kind: "tool" }>;

const DELEGATE = "delegate";

const STATUS_LABEL: Record<ToolStatus, string> = {
  running: vi.toolRunning,
  done: vi.toolDone,
  failed: vi.toolFailed,
  awaiting: vi.toolAwaiting,
  denied: vi.toolDenied,
};

/** A card has no coloured node beside it the way a timeline row does, so the icon is the
 *  fastest read of the state; the word beside it says the same for anyone who needs it. */
const STATUS_ICON: Record<ToolStatus, IconName> = {
  running: "spinner",
  done: "check",
  failed: "alert",
  awaiting: "pause",
  denied: "close",
};

function Status({ status, label }: { status: ToolStatus; label: string }) {
  return (
    <span className={`tool-status ${status}`}>
      <Icon name={STATUS_ICON[status]} />
      {label}
    </span>
  );
}

/**
 * Tool arguments as one readable line of `name=value` pairs.
 *
 * Runs recorded before the store kept arguments as a mapping hold them as a
 * single stringified line instead. `Object.entries` walks a string by index, so
 * such a row came out as one pair per character; showing the line as it stands
 * is the closest thing to the truth we still have about those runs.
 */
export function summarizeArguments(args: Record<string, unknown> | string): string {
  if (typeof args === "string") return args;
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
        <span className="tool-name">
          <Icon name="wrench" className="tool-icon" />
          {item.name}
        </span>
        <Status status={item.status} label={STATUS_LABEL[item.status]} />
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
        <span className="tool-name">
          {target ? (
            <AgentAvatar id={target} name={name} size="sm" />
          ) : (
            <Icon name="handoff" className="tool-icon" />
          )}
          {vi.delegateTo.replace("{agent}", name)}
        </span>
        <Status
          status={item.status}
          label={item.status === "running" ? vi.delegateRunning : STATUS_LABEL[item.status]}
        />
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
