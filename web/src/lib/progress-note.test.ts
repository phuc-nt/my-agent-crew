// The progress note across every layer that has to agree about it: the live reducer,
// the row mapping, the progress counter, the chat thread and the status line.
//
// They are tested together because the bug they guard against is a disagreement. The
// note is drawn twice — once from the live event and once from the server's stored step
// — and if the two layers shape it differently the row changes under the reader at the
// moment the run settles.
import { describe, expect, it } from "vitest";
import type { AgentEvent, RunInfo } from "../api/types";
import { applyRunEvent } from "../state/activity-reducer";
import { threadReducer, emptyThread, type ThreadState } from "../state/thread-reducer";
import { noteText, PROGRESS_NOTE_TOOL, runRows } from "./run-rows";
import { stepProgress, stepState } from "./run-progress";

function run(overrides: Partial<RunInfo> = {}): RunInfo {
  return {
    id: "r1",
    agent_id: "default",
    conversation_id: "c1",
    source: "chat",
    title: "t",
    status: "running",
    started_at: "2026-09-19T08:00:00Z",
    finished_at: null,
    spent_usd: 0,
    unknown_cost_calls: 0,
    summary: "",
    steps: [],
    ...overrides,
  };
}

const noteCall = { type: "tool_call", tool_call_id: "n1", name: PROGRESS_NOTE_TOOL, arguments: { text: "Đang tìm hợp đồng" } } as const;

describe("a note on a live run", () => {
  it("becomes a note step rather than a tool step", () => {
    // As a tool step it would have `ok: null`, and so spin a spinner for the rest of
    // the run on a sentence that was finished the moment it was written.
    const after = applyRunEvent(run(), noteCall);
    expect(after.steps).toHaveLength(1);
    expect(after.steps[0]).toMatchObject({ kind: "note", text: "Đang tìm hợp đồng", duration_ms: 0 });
  });

  it("is painted done, never running or failed", () => {
    const after = applyRunEvent(run(), noteCall);
    expect(stepState(after.steps[0], "running")).toBe("done");
    // A note has no `ok` field, so a missing branch here would fall through and paint
    // it as a failure on every settled run.
    expect(stepState(after.steps[0], "done")).toBe("done");
  });

  it("adds no second step when its result arrives", () => {
    const opened = applyRunEvent(run(), noteCall);
    const closed = applyRunEvent(opened, {
      type: "tool_result",
      tool_call_id: "n1",
      name: PROGRESS_NOTE_TOOL,
      ok: true,
      output: "Đã báo tiến trình.",
    });
    expect(closed.steps.map((s) => s.kind)).toEqual(["note"]);
  });

  it("leaves a real tool call alone", () => {
    const opened = applyRunEvent(run(), { type: "tool_call", tool_call_id: "t1", name: "shell_run", arguments: {} });
    const closed = applyRunEvent(opened, { type: "tool_result", tool_call_id: "t1", name: "shell_run", ok: true, output: "ok" });
    expect(closed.steps[0]).toMatchObject({ kind: "tool", name: "shell_run", ok: true });
  });
});

describe("a note in the timeline", () => {
  const withNote = run({
    steps: [{ kind: "note", text: "Đang đọc tệp", duration_ms: 0 }],
  });

  it("is labelled with its own sentence", () => {
    const [row] = runRows(withNote);
    expect(row.kind).toBe("note");
    expect(row.label).toBe("Đang đọc tệp");
  });

  it("never merges with the note beside it", () => {
    // Two notes say different things even when the merge rule cannot see the difference,
    // so collapsing them to "×2" would lose what the agent actually said.
    const two = run({
      steps: [
        { kind: "note", text: "Đang đọc tệp", duration_ms: 0 },
        { kind: "note", text: "Đang đọc tệp", duration_ms: 0 },
      ],
    });
    expect(runRows(two)).toHaveLength(2);
  });

  it("is left out of every step count shown beside the run", () => {
    // The card header, the conversation bar and the cost row all print a step count
    // next to a progress bar that excludes notes. Counting raw steps in any of them
    // makes the card say "3 bước" above a bar reading "2/2".
    const mixed = run({
      status: "done",
      steps: [
        { kind: "note", text: "Đang chạy", duration_ms: 0 },
        { kind: "tool", name: "shell_run", tool_call_id: "t1", arguments: {}, ok: true, output: "ok", duration_ms: 10 },
        { kind: "model", model: "m", provider: "p", chars: 10, cost_usd: 0.001, tool_calls: [], preview: "", duration_ms: 5 },
      ],
    });
    expect(mixed.steps).toHaveLength(3);
    expect(stepProgress(mixed).total).toBe(2);
  });

  it("is left out of the progress counter", () => {
    // Counted, a note would land on both sides of the fraction: an agent that explains
    // itself before each of three tool calls would read "6/8" where a silent one reads
    // "3/4", so talking would look like falling behind.
    const mixed = run({
      status: "done",
      steps: [
        { kind: "note", text: "Đang chạy", duration_ms: 0 },
        { kind: "tool", name: "shell_run", tool_call_id: "t1", arguments: {}, ok: true, output: "ok", duration_ms: 10 },
      ],
    });
    expect(stepProgress(mixed)).toEqual({ done: 1, total: 1 });
  });
});

describe("a note in the chat thread", () => {
  function send(state: ThreadState, event: AgentEvent): ThreadState {
    return threadReducer(state, { type: "event", event });
  }

  it("is an aside, not a tool card waiting on an output", () => {
    const after = send(emptyThread, noteCall);
    expect(after.items).toHaveLength(1);
    expect(after.items[0]).toMatchObject({ kind: "note", text: "Đang tìm hợp đồng" });
  });

  it("survives its own result without becoming a failed tool", () => {
    const opened = send(emptyThread, noteCall);
    const after = send(opened, { type: "tool_result", tool_call_id: "n1", name: PROGRESS_NOTE_TOOL, ok: true, output: "ok" });
    expect(after.items).toEqual(opened.items);
  });

  it("arrives as a note when announced on the assistant message too", () => {
    // Tool calls reach the thread by two routes; a note must be a note on both.
    const after = send(emptyThread, {
      type: "assistant_message",
      message_id: "m1",
      content: "",
      tool_calls: [{ id: "n1", name: PROGRESS_NOTE_TOOL, arguments: { text: "Đang mở sổ" } }],
      provider: "p",
      model: "m",
      cost_usd: null,
    });
    expect(after.items[0]).toMatchObject({ kind: "note", text: "Đang mở sổ" });
  });
});

describe("noteText", () => {
  it("collapses to one line, so the row it sits in stays one row", () => {
    expect(noteText({ text: "  đang   tìm\n\ntài liệu  " })).toBe("đang tìm tài liệu");
  });

  it("cuts at the same length the server cuts at", () => {
    // If the two differed, a long note would visibly change when the run settled and
    // the server's copy replaced the live one.
    expect(noteText({ text: "a".repeat(500) })).toHaveLength(200);
  });

  it("treats a missing text as empty rather than throwing", () => {
    expect(noteText({})).toBe("");
  });
});
