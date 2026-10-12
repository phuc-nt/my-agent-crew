import { notYetListed, withNested, workOf } from "../lib/nested-calls";
import { isAnswered } from "../lib/run-progress";
import { noteText, PROGRESS_NOTE_TOOL } from "../lib/run-rows";
import { preview, toolOutputPreview } from "../lib/step-preview";
import type { AgentEvent, NestedToolCall, RunInfo, RunStep } from "../api/types";

type ToolStep = Extract<RunStep, { kind: "tool" }>;

/** Where the step of a call stands, the latest of them: as on the server, a call made
 *  again after a restart is told by the step it left last, not the first of its id. */
function toolStepAt(steps: RunStep[], toolCallId: string): number {
  return steps.findLastIndex((s) => s.kind === "tool" && s.tool_call_id === toolCallId);
}

/** Client-side twin of the server's step builder so live runs show steps before they finish. */
export function applyRunEvent(run: RunInfo, e: AgentEvent): RunInfo {
  const steps: RunStep[] = [...run.steps];
  let { spent_usd, unknown_cost_calls, summary } = run;
  // A call the provider put no price on is counted apart instead of guessed at.
  const bill = (cost: number | null) => {
    if (cost === null) unknown_cost_calls += 1;
    else spent_usd += cost;
  };
  const billNested = (calls: NestedToolCall[]) => {
    for (const call of calls) if (call.metered) bill(call.cost_usd);
  };
  switch (e.type) {
    case "assistant_message": {
      // A child's answer handed on as this reply: no model spoke, so there is no step
      // and no bill. The delegate step already shows the answer.
      if (e.provider === null) break;
      // A run read mid-call carries that call open; its answer closes it rather than
      // standing beside it as a second call.
      const last = steps[steps.length - 1];
      const open = last?.kind === "model" && !isAnswered(last) ? last : null;
      const answered: RunStep = {
        kind: "model",
        first_token_ms: open?.first_token_ms,
        // This reducer skips deltas, so a snapshot's count stops where the snapshot was
        // taken; the answer is the whole of what streamed.
        chars: Math.max(open?.chars ?? 0, e.content.length),
        provider: e.provider,
        model: e.model,
        cost_usd: e.cost_usd,
        // Kept as the server keeps them, so a live card can show how much of the prompt the
        // cache served without waiting for the run to finish and be read back.
        prompt_tokens: e.prompt_tokens,
        cached_tokens: e.cached_tokens,
        thinking: open?.thinking,
        tool_calls: e.tool_calls.map((c) => c.name),
        preview: preview(e.content),
        duration_ms: null,
      };
      if (open) steps[steps.length - 1] = answered;
      else steps.push(answered);
      bill(e.cost_usd);
      if (e.content) summary = preview(e.content);
      break;
    }
    case "tool_call":
      if (e.name === PROGRESS_NOTE_TOOL) {
        // Closed the moment it is written, exactly as the server writes it: a note is
        // finished as soon as it is said, and an open one would spin a spinner on a
        // sentence for the rest of the run.
        steps.push({ kind: "note", text: noteText(e.arguments), duration_ms: 0 });
        break;
      }
      {
        // As on the server, a call made again after a restart takes the step it left open
        // instead of a second one. What a script called before the restart is not what it
        // calls now: those calls stay billed, since they were paid for, and leave the list.
        const again = toolStepAt(steps, e.tool_call_id);
        const open = again >= 0 ? (steps[again] as ToolStep) : null;
        if (open && open.ok === null) {
          const { calls: _before, ...reopened } = open;
          steps[again] = reopened;
          break;
        }
      }
      steps.push({
        kind: "tool",
        name: e.name,
        tool_call_id: e.tool_call_id,
        arguments: e.arguments,
        ok: null,
        output: null,
        duration_ms: null,
      });
      break;
    case "tool_result": {
      // The note step was already written and closed by its call, and it carries no
      // tool_call_id to find. Without this the search below would miss it, which is
      // harmless — but the step must not be patched with an ok flag either way.
      if (e.name === PROGRESS_NOTE_TOOL) break;
      const at = toolStepAt(steps, e.tool_call_id);
      if (at < 0) break;
      const step = steps[at] as ToolStep;
      // As on the server, what a script called on its own is kept on the script's step, as
      // the script wrote it: none of those calls had a step, so this is the one place they
      // show. Those heard while it ran are in the totals already; the rest are billed here,
      // which is every one of them for a script that ran beside other calls.
      const work = workOf(e);
      if (work.calls) billNested(notYetListed(step.calls ?? [], work.calls));
      steps[at] = { ...step, ok: e.ok, output: toolOutputPreview(e.output, e.ok), ...work };
      break;
    }
    case "nested_call": {
      // As on the server: listed on the script's step by its place among the script's
      // calls, and billed the once it is first heard. A script whose step is not here — a
      // run this tab holds no call of — is told whole by the run the server sends next.
      const at = toolStepAt(steps, e.tool_call_id);
      if (at < 0) break;
      const step = steps[at] as ToolStep;
      const { calls, added } = withNested(step.calls, e.index, e.call);
      steps[at] = { ...step, calls };
      if (added) billNested([e.call]);
      break;
    }
    case "approval_required": {
      // As on the server, a question is summarised by what it asked and leaves its step
      // open. The open step is what labels the pause "đang hỏi bạn": without it a run that
      // paused on the live stream reads as a permission request until the list reloads.
      const asked = e.kind === "question" && typeof e.arguments.question === "string" ? e.arguments.question : "";
      if (asked) {
        steps.push({ kind: "question", question: preview(asked), duration_ms: null });
        summary = asked;
        break;
      }
      summary = e.reason ? `${e.name} (${e.reason})` : e.name;
      break;
    }
    case "halted":
      summary = e.reason;
      spent_usd = e.spent_usd;
      break;
    case "error":
      summary = e.message;
      break;
    case "done":
      spent_usd = e.spent_usd;
      unknown_cost_calls = e.unknown_cost_calls;
      break;
    case "route_fallback": {
      // As on the server, an open call moves after the fallback: it now waits on the next
      // route, and left ahead of it the answer would open a second call instead.
      const fallback: RunStep = { kind: "fallback", provider: e.provider, model: e.model, error: preview(e.error), duration_ms: null };
      const last = steps[steps.length - 1];
      if (last?.kind === "model" && !isAnswered(last)) steps.splice(steps.length - 1, 0, fallback);
      else steps.push(fallback);
      break;
    }
    case "escalated": {
      // As on the server, the move takes the place of a call left open: no route of the
      // agent's own answered it, and the call made next on the new route is a step of its
      // own. A move made for a loop finds no call open and stands after the refused one.
      const moved: RunStep = { kind: "escalation", reason: e.reason, provider: e.provider, model: e.model, duration_ms: null };
      if (e.error) moved.error = preview(e.error);
      const last = steps[steps.length - 1];
      if (last?.kind === "model" && !isAnswered(last)) steps[steps.length - 1] = moved;
      else steps.push(moved);
      break;
    }
    case "steer":
      // Shown the way a note is, and shortened by the same function the server shortens
      // it with (`note_text` in `activity/steps.py`), so the row does not change text
      // once the server's own stored step replaces this live one.
      steps.push({ kind: "steer", text: noteText(e.text), duration_ms: 0 });
      break;
    // Never reaches the activity stream: a stream nothing is watching for it carries only
    // the one `queued` event, which the sending hook intercepts before this reducer runs, and
    // the canvas note of a message goes to the tab that sent it and no one else.
    // Listed so the switch stays exhaustive against a stale tab that somehow still sees them.
    // The pieces of a canvas being written are no step of a run: the call they add up to is.
    case "queued":
    case "user_context":
    case "tool_call_delta":
    case "text_delta":
    case "thinking":
    case "model_call":
      break;
  }
  return { ...run, steps, spent_usd, unknown_cost_calls, summary };
}
