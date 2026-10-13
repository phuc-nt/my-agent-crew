import { vi } from "../i18n/vi";
import {
  delegateAgent,
  delegateReason,
  delegateTask,
  delegateTone,
  parseDelegateResult,
} from "../lib/delegate-result";
import type { ThreadItem, ToolStatus } from "../state/thread-reducer";
import { CanvasCard, type CanvasLinks, isCanvasWrite } from "./canvas/canvas-card";
import { DelegateCanvases } from "./canvas/delegate-canvases";
import { ScriptCanvases } from "./canvas/script-canvases";
import { ScreenshotThumb } from "./screenshot-thumb";
import { ScriptReport } from "./script-calls";
import { summarizeArguments, ToolArgsDetail } from "./tool-args-detail";
import { ToolOutput } from "./tool-output";
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
  stopped: vi.toolStopped,
};

/** A card has no coloured node beside it the way a timeline row does, so the icon is the
 *  fastest read of the state; the word beside it says the same for anyone who needs it. */
const STATUS_ICON: Record<ToolStatus, IconName> = {
  running: "spinner",
  done: "check",
  failed: "alert",
  awaiting: "pause",
  denied: "close",
  stopped: "stop",
};

/** Refused or failed, what the call handed back is the reason either way. */
const didFail = (status: ToolStatus) => status === "failed" || status === "denied";

function Status({ status, label }: { status: ToolStatus; label: string }) {
  return (
    <span className={`tool-status ${status}`}>
      <Icon name={STATUS_ICON[status]} />
      {label}
    </span>
  );
}

interface Props {
  item: ToolItem;
  /** Whose conversation this is, which is whose workspace a screenshot was saved in. */
  agentId?: string;
  /** Names the agent ids the crew knows, so a card can show a name instead of an id. */
  agentName?: (id: string) => string;
  /** Opens the child conversation this call created; absent means the button is hidden. */
  onOpenConversation?: (conversationId: string) => void;
  /** Lets a write to a canvas be drawn as that canvas, with a way to open it; absent keeps the plain card. */
  canvas?: CanvasLinks;
}

export function ToolCallCard({ item, agentId, agentName, onOpenConversation, canvas }: Props) {
  if (item.name === DELEGATE) {
    return <DelegateCard item={item} agentName={agentName} onOpenConversation={onOpenConversation} canvas={canvas} />;
  }
  if (canvas && isCanvasWrite(item)) return <CanvasCard item={item} canvas={canvas} />;
  return (
    <>
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
        <ToolArgsDetail args={item.arguments} />
        {/* As on the run's step: what a script called on its own, above what it printed. */}
        <ScriptReport
          work={item}
          settled={item.status === "done" || item.status === "failed"}
          onOpenConversation={onOpenConversation}
        />
        {/* As on the run's step: the picture a screenshot saved, once the call went through. */}
        {item.status === "done" && <ScreenshotThumb agentId={agentId} toolName={item.name} output={item.output} />}
        {item.output && <ToolOutput text={item.output} failed={didFail(item.status)} />}
      </div>
      {/* A canvas a script wrote has its card under the script's, as one the agent wrote itself has. */}
      {canvas && <ScriptCanvases item={item} canvas={canvas} />}
    </>
  );
}

/**
 * A handed-off task, shown as the job rather than as a tool call: who took it, what they
 * were asked, and — once they answer — how it went, what it cost and the canvases they
 * wrote. The child runs as its own conversation, so the card offers a way in rather than
 * inlining the whole thing.
 */
function DelegateCard({ item, agentName, onOpenConversation, canvas }: Props) {
  const target = delegateAgent(item.arguments);
  const task = delegateTask(item.arguments);
  const result = item.output ? parseDelegateResult(item.output) : null;
  const reason = result ? delegateReason(result) : "";
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
          <span
            className="delegate-chip"
            data-testid="delegate-status"
            data-tone={delegateTone(result)}
            title={reason || undefined}
          >
            {result.outcome ? (vi.delegateOutcome[result.outcome] ?? result.outcome) : result.status}
          </span>
          {reason && (
            <span className="delegate-reason" data-testid="delegate-reason">
              {reason}
            </span>
          )}
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
      {canvas && result && <DelegateCanvases canvases={result.canvases} canvas={canvas} />}
      {item.output && <ToolOutput text={result ? result.reply : item.output} failed={didFail(item.status)} />}
    </div>
  );
}
