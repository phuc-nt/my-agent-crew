import { useState } from "react";
import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { isSettled } from "../lib/run-progress";
import { runRows, type RunRow } from "../lib/run-rows";
import type { RunGroup } from "../state/activity-reducer";
import { formatUsd } from "./budget-indicator";
import { RunProgressHeader } from "./run-progress-header";
import { summarizeArguments } from "./tool-call-card";

export function formatClock(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
}

interface Props {
  run: RunInfo;
  agentName: string;
  expanded?: boolean;
  onOpenConversation?: (conversationId: string) => void;
}

/** One run as a card: who, what, status, cost, then the step timeline when expanded. */
export function RunCard({ run, agentName, expanded = false, onOpenConversation }: Props) {
  const [open, setOpen] = useState(expanded);
  const live = !isSettled(run.status);
  return (
    <article className={`run-card ${run.status}`} data-testid="run-card" data-status={run.status}>
      <button type="button" className="run-summary" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className={`status-dot ${run.status}`} aria-hidden="true" />
        <span className="run-main">
          <span className="run-title">
            <strong>{agentName}</strong> · {run.title || vi.runSource(run.source)}
          </span>
          <span className="run-meta muted">
            {vi.runStatus[run.status]} · {formatClock(run.started_at)} · {vi.runSteps(run.steps.length)} ·{" "}
            {formatUsd(run.spent_usd)}
            {run.unknown_cost_calls > 0 && ` · ? ${run.unknown_cost_calls}`}
            {live && <span className="badge live"> {vi.liveNow}</span>}
          </span>
          {run.summary && <span className="run-preview muted">{run.summary}</span>}
        </span>
      </button>
      {open && (
        <div className="run-body">
          {/* The live header sits above the steps, so the answer to "what is it
              doing" is in one fixed place rather than at the bottom of a list
              that grows while you read it. */}
          {(live || run.steps.length > 0) && <RunProgressHeader run={run} />}
          {run.steps.length === 0 ? (
            <p className="muted">{vi.thinking}</p>
          ) : (
            <ol className="run-steps">
              {runRows(run).map((row) => (
                <StepRow key={row.key} row={row} />
              ))}
            </ol>
          )}
          {run.conversation_id && onOpenConversation && (
            <button
              type="button"
              className="link-button"
              onClick={() => onOpenConversation(run.conversation_id as string)}
            >
              {vi.openConversation}
            </button>
          )}
        </div>
      )}
    </article>
  );
}

const STATE_LABEL: Record<RunRow["state"], string> = {
  running: vi.toolRunning,
  done: vi.toolDone,
  failed: vi.toolFailed,
  stalled: vi.toolStalled,
};

/**
 * Whether the state deserves its own word on the row.
 *
 * A plain success does not: a settled row that says nothing is a row that went
 * fine, which is what the eye is looking to skip past. Neither does a fallback,
 * which is a failure by definition — "đổi tuyến" already says a route gave up,
 * and adding "lỗi" beside it only costs the row the width it needs to stay on
 * one line.
 */
function showState(row: RunRow): boolean {
  if (row.state === "done") return false;
  if (row.kind === "fallback") return false;
  return true;
}

/**
 * One node on the rail.
 *
 * The class list carries both axes the stylesheet needs: the kind, which
 * colours the node and never changes, and the state, which the row around it
 * expresses. They are kept separate on purpose — see run-timeline.css.
 *
 * No glyph sits next to the label. The node is already coloured by kind, and a
 * second symbol saying the same thing only competes with it.
 */
function StepRow({ row }: { row: RunRow }) {
  const [showOutput, setShowOutput] = useState(false);
  const { step } = row;
  const duration = row.durationMs !== null ? vi.stepDuration(row.durationMs) : null;

  return (
    <li className={`step ${row.kind} ${row.state}`} data-testid="run-step" data-state={row.state}>
      <span className="step-head">
        <span className="step-name">
          <span className="step-kind">{row.label}</span>
          {/* The kind in words. A label on its own is ambiguous — "sonnet" and
              "openrouter:glm" both read as names until something says which one
              answered and which one was abandoned. A tool row is the exception:
              its name is a verb already. */}
          {row.kind === "model" && <span className="step-role muted">{vi.stepModel}</span>}
          {row.kind === "fallback" && <span className="step-role muted">{vi.stepFallback}</span>}
          {row.kind === "delegate" && <span className="step-role muted">{vi.stepDelegate}</span>}
          {row.repeat > 1 && (
            <span className="step-repeat tabular" title={vi.runStepCount(row.repeat, row.repeat)}>
              {vi.stepRepeat(row.repeat)}
            </span>
          )}
          {showState(row) ? (
            <span className={`step-state ${row.state}`}>{STATE_LABEL[row.state]}</span>
          ) : (
            /* Still spoken, since on these rows the state is carried only by
               colour or by a word that implies it. */
            <span className="sr-only">{STATE_LABEL[row.state]}</span>
          )}
        </span>
        {duration && <span className="step-time tabular">{duration}</span>}
      </span>
      {step.kind === "model" && (
        <span className="step-detail">
          {vi.stepChars(step.chars)} · {step.cost_usd === null ? vi.stepCostUnknown : formatUsd(step.cost_usd)}
          {step.tool_calls.length > 0 && ` · → ${step.tool_calls.join(", ")}`}
        </span>
      )}
      {step.kind === "model" && step.preview && <span className="step-preview muted">{step.preview}</span>}
      {step.kind === "fallback" && <span className="step-detail">{step.error}</span>}
      {step.kind === "tool" && <span className="tool-arguments">{summarizeArguments(step.arguments) || "—"}</span>}
      {step.kind === "tool" && step.output && (
        <>
          <button type="button" className="link-button" onClick={() => setShowOutput((s) => !s)}>
            {showOutput ? vi.hideOutput : vi.showOutput}
          </button>
          {showOutput && <pre className="tool-output">{step.output}</pre>}
        </>
      )}
    </li>
  );
}

/**
 * A run with the work it handed out shown underneath it.
 *
 * One level only: a delegated agent cannot delegate on, so a child never has children.
 * The children stay visible after the parent finishes, since that is usually the moment
 * someone wants to see what each of them actually did.
 */
export function RunGroupCard({
  group,
  agentName,
  expanded = false,
  onOpenConversation,
}: {
  group: RunGroup;
  agentName: (id: string) => string;
  expanded?: boolean;
  onOpenConversation?: (conversationId: string) => void;
}) {
  return (
    <div className="run-group" data-testid="run-group">
      <RunCard
        run={group.run}
        agentName={agentName(group.run.agent_id)}
        expanded={expanded}
        onOpenConversation={onOpenConversation}
      />
      {group.children.length > 0 && (
        <div className="run-children" data-testid="run-children">
          {group.children.map((child) => (
            <RunCard
              key={child.id}
              run={child}
              agentName={agentName(child.agent_id)}
              onOpenConversation={onOpenConversation}
            />
          ))}
        </div>
      )}
    </div>
  );
}
