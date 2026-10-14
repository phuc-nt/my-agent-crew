import { vi } from "../i18n/vi";
import type { FramePaths } from "../lib/desktop-frame";
import { modelUsageParts } from "../lib/format-usage";
import { isAnswered } from "../lib/run-progress";
import type { RunRow } from "../lib/run-rows";
import { formatUsd } from "./budget-indicator";
import { ScreenshotThumb } from "./screenshot-thumb";
import { ScriptReport } from "./script-calls";
import { summarizeArguments } from "./tool-args-detail";
import { ToolOutput } from "./tool-output";

const STATE_LABEL: Record<RunRow["state"], string> = {
  running: vi.toolRunning,
  done: vi.toolDone,
  failed: vi.toolFailed,
  stalled: vi.toolStalled,
  waiting: vi.toolWaiting,
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
  // A call still answering is labelled by what it is doing, which already says so.
  if (row.kind === "model" && row.state === "running") return false;
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
interface Props {
  row: RunRow;
  /** Whose run this is, which is whose workspace a step's screenshot was saved in. */
  agentId?: string;
  /** The desktop pictures the run's screenshots saved, by frame. */
  frames?: FramePaths;
  onOpenConversation?: (conversationId: string) => void;
}

export function StepRow({ row, agentId, frames, onOpenConversation }: Props) {
  const { step } = row;
  // A note's duration is always zero — it is stamped and closed on the same clock. "0 ms"
  // on every note row is noise that says nothing about the work the note describes. A
  // steer step is the same: said and done in the same instant, by a person instead.
  // A move to the escalation route made for a loop is decided on the spot and takes no
  // time either; one made for an error took as long as the call that never answered.
  const instant = row.kind === "note" || row.kind === "steer" || (row.kind === "escalation" && !row.durationMs);
  const duration = row.durationMs !== null && !instant ? vi.stepDuration(row.durationMs) : null;

  return (
    <li className={`step ${row.kind} ${row.state}`} data-testid="run-step" data-state={row.state}>
      <span className="step-head">
        <span className="step-name">
          <span className="step-kind">{row.label}</span>
          {/* The kind in words. A label on its own is ambiguous — "sonnet" and
              "openrouter:glm" both read as names until something says which one
              answered and which one was abandoned. A tool row is the exception:
              its name is a verb already. */}
          {row.kind === "model" && row.state !== "running" && <span className="step-role muted">{vi.stepModel}</span>}
          {row.kind === "fallback" && <span className="step-role muted">{vi.stepFallback}</span>}
          {row.kind === "escalation" && <span className="step-role muted">{vi.stepEscalation}</span>}
          {row.kind === "delegate" && <span className="step-role muted">{vi.stepDelegate}</span>}
          {/* The label is the question itself, so without this the row reads as a
              statement the agent made rather than one it is waiting on. */}
          {row.kind === "question" && <span className="step-role muted">{vi.stepQuestion}</span>}
          {/* Same reason: the label is a sentence the agent wrote, and without a word
              naming it the row reads as the agent's answer rather than an aside. */}
          {row.kind === "note" && <span className="step-role muted">{vi.stepNote}</span>}
          {/* Same reason again, but the sentence is a person's, not the agent's — without
              this the row reads as something the agent itself said. */}
          {row.kind === "steer" && <span className="step-role muted">{vi.stepSteer}</span>}
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
      {step.kind === "model" && isAnswered(step) && (
        <span className="step-detail">
          {[
            ...modelUsageParts(step),
            vi.stepChars(step.chars),
            step.cost_usd == null ? vi.stepCostUnknown : formatUsd(step.cost_usd),
          ].join(" · ")}
          {step.tool_calls.length > 0 && ` · → ${step.tool_calls.join(", ")}`}
        </span>
      )}
      {step.kind === "model" && step.preview && <span className="step-preview muted">{step.preview}</span>}
      {step.kind === "fallback" && <span className="step-detail">{step.error}</span>}
      {step.kind === "escalation" && (
        <span className="step-detail">
          {vi.stepEscalationReason[step.reason]}
          {step.error && ` — ${step.error}`}
        </span>
      )}
      {step.kind === "tool" && (
        <span className="tool-arguments">
          {(step.arguments !== undefined && summarizeArguments(step.arguments)) || "—"}
        </span>
      )}
      {/* The model read a shortened output. Saying so here is what stops a thin answer
          from being read as the whole picture when it was built on a thinned source. */}
      {step.kind === "tool" && step.shaped && (
        <span className="step-detail muted" data-testid="step-shaped">
          {vi.stepShaped(step.shaped.kind, step.shaped.original_chars)}
        </span>
      )}
      {/* A tool that asked a model itself: its price is in the run's total, so the row
          that spent it says so instead of leaving the total larger than its model rows. */}
      {step.kind === "tool" && step.cost_usd !== undefined && (
        <span className="step-detail muted" data-testid="step-tool-cost">
          {vi.stepToolCost(step.cost_usd === null ? vi.stepCostUnknown : formatUsd(step.cost_usd))}
        </span>
      )}
      {/* What a script called on its own. Above its output, since the calls are what was
          done and the output only what the script chose to say about it. A task it handed
          to another agent has no step of its own on this rail, so the way into that
          agent's conversation is on the call. */}
      {step.kind === "tool" && (
        <ScriptReport work={step} settled={step.ok !== null} onOpenConversation={onOpenConversation} />
      )}
      {/* The picture a screenshot saved, once the call is known to have gone through. */}
      {step.kind === "tool" && step.ok === true && (
        <ScreenshotThumb agentId={agentId} toolName={step.name} output={step.output} frames={frames} />
      )}
      {step.kind === "tool" && step.output && <ToolOutput text={step.output} failed={step.ok === false} />}
    </li>
  );
}
