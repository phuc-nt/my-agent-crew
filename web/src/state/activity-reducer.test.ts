import { describe, expect, it } from "vitest";
import type { NestedToolCall, RunInfo } from "../api/types";
import {
  activityReducer,
  applyRunEvent,
  emptyActivity,
  liveRuns,
  needsAttention,
  parentConversationId,
  runGroups,
  runsForConversation,
  sortedRuns,
} from "./activity-reducer";

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

describe("applyRunEvent", () => {
  it("turns assistant messages into model steps and tracks honest cost", () => {
    const a = applyRunEvent(run(), {
      type: "assistant_message",
      message_id: "m1",
      content: "x".repeat(200),
      tool_calls: [{ id: "tc", name: "read_file", arguments: {} }],
      provider: "openrouter",
      model: "deepseek",
      cost_usd: 0.002,
    });
    expect(a.steps).toHaveLength(1);
    expect(a.steps[0]).toMatchObject({ kind: "model", chars: 200, model: "deepseek", tool_calls: ["read_file"] });
    expect((a.steps[0] as { preview: string }).preview.endsWith("…")).toBe(true);
    expect(a.spent_usd).toBeCloseTo(0.002);
    // A local model reports no price: counted as unknown, never as free.
    const b = applyRunEvent(a, {
      type: "assistant_message",
      message_id: "m2",
      content: "",
      tool_calls: [],
      provider: "ollama",
      model: "llama3",
      cost_usd: null,
    });
    expect(b.unknown_cost_calls).toBe(1);
    expect(b.summary).toBe(a.summary);
  });

  it("completes the model step a snapshot caught mid-call instead of adding a second", () => {
    // A tab that connects while the model is answering gets the run with that call open:
    // no answer, no price, no tool calls yet. The answer closes that step, as on the server.
    const midCall = run({ steps: [{ kind: "model", chars: 5, first_token_ms: 300, duration_ms: null }] });
    const next = applyRunEvent(midCall, {
      type: "assistant_message",
      message_id: "m1",
      content: "xin chào",
      tool_calls: [],
      provider: "openrouter",
      model: "deepseek",
      cost_usd: 0.001,
    });
    expect(next.steps).toHaveLength(1);
    // Five characters had streamed when the snapshot was taken; the answer is all eight.
    expect(next.steps[0]).toMatchObject({ kind: "model", chars: 8, first_token_ms: 300, model: "deepseek", cost_usd: 0.001 });
    expect(next.spent_usd).toBeCloseTo(0.001);
  });

  // The cache share is what tells a broken prompt cache from a working one; a live card
  // that dropped these would show it only after the run was read back from the store.
  it("keeps the prompt and cached tokens of a finished call, and that it thought first", () => {
    const midCall = run({ steps: [{ kind: "model", chars: 0, first_token_ms: 900, thinking: true, duration_ms: null }] });
    const next = applyRunEvent(midCall, {
      type: "assistant_message",
      message_id: "m1",
      content: "xong",
      tool_calls: [],
      provider: "openrouter",
      model: "deepseek",
      cost_usd: 0.001,
      prompt_tokens: 12_300,
      cached_tokens: 8_100,
    });
    expect(next.steps[0]).toMatchObject({ prompt_tokens: 12_300, cached_tokens: 8_100, thinking: true, first_token_ms: 900 });
  });

  it("puts a fallback ahead of the call a snapshot caught open, so the answer closes that call", () => {
    const midCall = run({ steps: [{ kind: "model", chars: 0, first_token_ms: null, duration_ms: null }] });
    const fellBack = applyRunEvent(midCall, { type: "route_fallback", provider: "openrouter", model: "glm", error: "429" });
    const next = applyRunEvent(fellBack, {
      type: "assistant_message",
      message_id: "m1",
      content: "ok",
      tool_calls: [],
      provider: "openrouter",
      model: "deepseek",
      cost_usd: 0.001,
    });
    expect(next.steps.map((s) => s.kind)).toEqual(["fallback", "model"]);
    expect(next.steps[1]).toMatchObject({ model: "deepseek", chars: 2 });
  });

  it("adds no model step for a child's answer handed on whole, as the server does not", () => {
    const relayed = applyRunEvent(run({ summary: "delegate" }), {
      type: "assistant_message",
      message_id: "m2",
      content: "Có 3 tệp.",
      tool_calls: [],
      provider: null,
      model: null,
      cost_usd: 0,
    });
    expect(relayed.steps).toHaveLength(0);
    expect(relayed.unknown_cost_calls).toBe(0);
    expect(relayed.summary).toBe("delegate");
  });

  it("opens a tool step on tool_call and closes it with the matching tool_result", () => {
    const opened = applyRunEvent(run(), { type: "tool_call", tool_call_id: "tc", name: "shell_run", arguments: { command: "ls" } });
    expect(opened.steps[0]).toMatchObject({ kind: "tool", name: "shell_run", ok: null, output: null });
    const closed = applyRunEvent(opened, { type: "tool_result", tool_call_id: "tc", name: "shell_run", ok: false, output: "boom" });
    expect(closed.steps[0]).toMatchObject({ kind: "tool", ok: false, output: "boom" });
    const stray = applyRunEvent(closed, { type: "tool_result", tool_call_id: "zz", name: "x", ok: true, output: "" });
    expect(stray.steps).toHaveLength(1);
  });

  it("keeps what a script called on the step of the script, as the server stores it", () => {
    const calls = [
      { name: "mcp__notion__search", arguments: { query: "kế hoạch" }, ok: true, output: "3 trang", ms: 120, cost_usd: 0.004, metered: true },
      { name: "workspace_read", arguments: { path: "a.md" }, ok: false, output: "không có tệp", ms: 4, cost_usd: null, metered: false },
    ];
    const opened = applyRunEvent(run(), { type: "tool_call", tool_call_id: "s1", name: "tool_script", arguments: { script: "…" } });
    const result = { type: "tool_result", tool_call_id: "s1", name: "tool_script", ok: true, output: "xong" } as const;

    const scripted = applyRunEvent(opened, { ...result, calls });
    expect(scripted.steps).toHaveLength(1);
    expect(scripted.steps[0]).toMatchObject({ kind: "tool", name: "tool_script", ok: true, output: "xong", calls });
    // No event listed these while the script ran, as for calls made side by side: the
    // one that paid a model is added to the card here, the moment the server adds it.
    expect(scripted.spent_usd).toBeCloseTo(0.004, 10);
    expect(scripted.unknown_cost_calls).toBe(0);

    // A tool that called nothing has no list, whether the server sent an empty one or,
    // being older than the bundle, none at all: the server stores none either.
    for (const none of [{}, { calls: [] }]) {
      const plain = applyRunEvent(opened, { ...result, ...none });
      expect(plain.steps[0]).toMatchObject({ ok: true, output: "xong" });
      expect(plain.steps[0]).not.toHaveProperty("calls");
    }
  });

  it("keeps the two measures of a script on its step, and none where the result has none", () => {
    const opened = applyRunEvent(run(), { type: "tool_call", tool_call_id: "s1", name: "tool_script", arguments: { script: "…" } });
    const result = { type: "tool_result", tool_call_id: "s1", name: "tool_script", ok: true, output: "xong" } as const;

    const measured = applyRunEvent(opened, { ...result, received_chars: 1_200, printed_chars: 80 });
    expect(measured.steps[0]).toMatchObject({ received_chars: 1_200, printed_chars: 80 });
    // Nought is a count, and is kept as one.
    const idle = applyRunEvent(opened, { ...result, received_chars: 0, printed_chars: 0 });
    expect(idle.steps[0]).toMatchObject({ received_chars: 0, printed_chars: 0 });
    // A tool that is no script, and a server older than the bundle: the step says nothing.
    for (const none of [{}, { received_chars: null, printed_chars: null }]) {
      const plain = applyRunEvent(opened, { ...result, ...none });
      expect(plain.steps[0]).not.toHaveProperty("received_chars");
      expect(plain.steps[0]).not.toHaveProperty("printed_chars");
    }
  });

  describe("what a script calls, heard as each call ends", () => {
    const search: NestedToolCall = { name: "mcp__notion__search", arguments: { query: "kế hoạch" }, ok: true, output: "3 trang", ms: 120, cost_usd: null, metered: false };
    const paid: NestedToolCall = { name: "pdf_read", arguments: { path: "a.pdf" }, ok: true, output: "Tổng chi 4,2 triệu.", ms: 1_500, cost_usd: 0.004, metered: true };
    const unpriced: NestedToolCall = { name: "image_read", arguments: { path: "a.png" }, ok: true, output: "một biểu đồ", ms: 900, cost_usd: null, metered: true };
    const open = (id = "s1") => ({ type: "tool_call", tool_call_id: id, name: "tool_script", arguments: { script: "…" } }) as const;
    const heard = (index: number, call: NestedToolCall, id = "s1") => ({ type: "nested_call", tool_call_id: id, index, call }) as const;
    const result = (calls: NestedToolCall[], id = "s1") => ({ type: "tool_result", tool_call_id: id, name: "tool_script", ok: true, output: "xong", calls }) as const;
    const after = (...events: Parameters<typeof applyRunEvent>[1][]) => events.reduce(applyRunEvent, run());

    it("lists the call on the step of the script, which stays open, and adds what it paid", () => {
      const one = after(open(), heard(0, search));
      expect(one.steps).toHaveLength(1);
      expect(one.steps[0]).toMatchObject({ kind: "tool", name: "tool_script", ok: null, output: null, calls: [search] });
      expect(one).toMatchObject({ spent_usd: 0, unknown_cost_calls: 0 });

      const two = applyRunEvent(one, heard(1, paid));
      expect(two.steps[0]).toMatchObject({ ok: null, calls: [search, paid] });
      expect(two.spent_usd).toBeCloseTo(0.004, 10);
      expect(two.unknown_cost_calls).toBe(0);
    });

    it("counts apart a call that paid a model at a price nobody gave", () => {
      const next = after(open(), heard(0, unpriced));
      expect(next).toMatchObject({ spent_usd: 0, unknown_cost_calls: 1 });
    });

    it("adds nothing for a call that was not charged, whatever figure rode along", () => {
      const next = after(open(), heard(0, { ...search, cost_usd: 0.5 }));
      expect(next).toMatchObject({ spent_usd: 0, unknown_cost_calls: 0 });
    });

    // A tab that joined late is handed the run with the calls so far, then may hear the
    // last of them once more on the stream: one place, one call, one charge.
    it("keeps a call heard twice once, and adds what it paid once", () => {
      const once = after(open(), heard(0, paid), heard(1, unpriced));
      const twice = [heard(0, paid), heard(1, unpriced), heard(1, unpriced)].reduce(applyRunEvent, once);
      expect(twice.steps[0]).toMatchObject({ calls: [paid, unpriced] });
      expect(twice.spent_usd).toBeCloseTo(0.004, 10);
      expect(twice.unknown_cost_calls).toBe(1);

      const joinedLate = run({
        spent_usd: 0.004,
        steps: [{ kind: "tool", name: "tool_script", tool_call_id: "s1", arguments: {}, ok: null, output: null, calls: [paid], duration_ms: null }],
      });
      expect(applyRunEvent(joinedLate, heard(0, paid)).spent_usd).toBeCloseTo(0.004, 10);
    });

    it("adds from the result only what no event listed, and keeps the calls in the order the script made them", () => {
      // Heard as they ended: the paid one first, though the script made it second.
      const running = after(open(), heard(0, paid), heard(1, unpriced));
      const later = { ...paid, arguments: { path: "b.pdf" }, cost_usd: 0.002 };

      const closed = applyRunEvent(running, result([search, paid, unpriced, later]));

      expect(closed.steps[0]).toMatchObject({ ok: true, calls: [search, paid, unpriced, later] });
      expect(closed.spent_usd).toBeCloseTo(0.006, 10);
      expect(closed.unknown_cost_calls).toBe(1);
    });

    it("adds nothing from a result whose every call was heard as it ended", () => {
      const closed = after(open(), heard(0, paid), heard(1, unpriced), result([paid, unpriced]));
      expect(closed.spent_usd).toBeCloseTo(0.004, 10);
      expect(closed.unknown_cost_calls).toBe(1);
    });

    // After a restart the server makes the call again: what the script called before is
    // not what it calls now, though what was paid for it stays paid.
    it("reuses the open step of a call made again, with the calls gone and the totals kept", () => {
      const before = after(open(), heard(0, paid));
      const again = applyRunEvent(before, open());
      expect(again.steps).toHaveLength(1);
      expect(again.steps[0]).toMatchObject({ kind: "tool", name: "tool_script", tool_call_id: "s1", ok: null });
      expect(again.steps[0]).not.toHaveProperty("calls");
      expect(again.spent_usd).toBeCloseTo(0.004, 10);

      // The first call of the new attempt is new, and is charged as such.
      const anew = applyRunEvent(again, heard(0, paid));
      expect(anew.steps[0]).toMatchObject({ calls: [paid] });
      expect(anew.spent_usd).toBeCloseTo(0.008, 10);
    });

    it("opens a new step for an id whose step was answered, and lists on the latest of the two", () => {
      const reused = after(open(), heard(0, search), result([search]), open(), heard(0, paid));
      expect(reused.steps).toHaveLength(2);
      expect(reused.steps[0]).toMatchObject({ ok: true, calls: [search] });
      expect(reused.steps[1]).toMatchObject({ ok: null, calls: [paid] });

      const closed = applyRunEvent(reused, result([paid]));
      expect(closed.steps[0]).toMatchObject({ ok: true, calls: [search] });
      expect(closed.steps[1]).toMatchObject({ ok: true, calls: [paid] });
      expect(closed.spent_usd).toBeCloseTo(0.004, 10);
    });

    // A model the script asked itself is listed under a name no tool has. It paid a model
    // like any other charged call, and nothing about its name changes how that is added.
    const classify: NestedToolCall = { name: "llm.classify", arguments: { text: "Kính gửi quý khách…", labels: '["hoá đơn", "khác"]' }, ok: true, output: "hoá đơn", ms: 812, cost_usd: 0.00021, metered: true };
    const summarise: NestedToolCall = { name: "llm.summarise", arguments: { text: "…", max_chars: 500 }, ok: true, output: "Khách xin hoãn hạn trả.", ms: 1_304, cost_usd: 0.0004, metered: true };

    it("adds what a model the script asked itself cost, once, on the step of the script", () => {
      const running = after(open(), heard(0, classify), heard(1, summarise), heard(1, summarise));
      expect(running.steps).toHaveLength(1);
      expect(running.steps[0]).toMatchObject({ name: "tool_script", calls: [classify, summarise] });
      expect(running.spent_usd).toBeCloseTo(0.00061, 10);

      const closed = applyRunEvent(running, result([classify, summarise]));
      expect(closed.steps).toHaveLength(1);
      expect(closed.spent_usd).toBeCloseTo(0.00061, 10);
      expect(closed.unknown_cost_calls).toBe(0);
    });

    it("counts a model call that failed at no known price among the calls nobody priced", () => {
      const failed = { ...classify, ok: false, output: "model không trả lời", cost_usd: null };
      const closed = after(open(), heard(0, failed), result([failed]));
      expect(closed).toMatchObject({ spent_usd: 0, unknown_cost_calls: 1 });
    });

    // A task the script handed to another agent. What that agent spent is its own
    // conversation's money: it rides on the call to be shown, and is no part of this run.
    const handedOff: NestedToolCall = { name: "delegate", arguments: { task: "Soạn thư trả lời khách", agent: "writer" }, ok: true, output: "conversation=3f9a1c0b7d2e status=done spent=$0.0123 steps=7 outcome=done Thư đã soạn xong.", ms: 48_211, cost_usd: null, metered: false, child_spent_usd: 0.0123 };

    it("leaves the run's spend where it was for a task handed off, whatever the other agent spent", () => {
      const before = after(open(), heard(0, paid));
      const running = applyRunEvent(before, heard(1, handedOff));
      expect(running.steps[0]).toMatchObject({ calls: [paid, handedOff] });
      expect(running.spent_usd).toBe(before.spent_usd);
      expect(running.unknown_cost_calls).toBe(0);

      // Heard once more, then named again by the result: one call still, and nothing added.
      const closed = [heard(1, handedOff), result([paid, handedOff])].reduce(applyRunEvent, running);
      expect(closed.steps[0]).toMatchObject({ ok: true, calls: [paid, handedOff] });
      expect(closed.spent_usd).toBe(before.spent_usd);
      expect(closed.unknown_cost_calls).toBe(0);
    });

    it("adds nothing for a handed-off task no event came for, which the result is first to name", () => {
      const closed = after(open(), result([handedOff]));
      expect(closed.steps[0]).toMatchObject({ calls: [handedOff] });
      expect(closed).toMatchObject({ spent_usd: 0, unknown_cost_calls: 0 });
    });

    // The figure is there only above zero, so one hearing may carry it and the other not.
    // Were it part of what makes a call the one it is, the call would be taken for a new
    // one when the result names it, and whatever it was charged would be added again.
    it("takes a call for the one it heard whether or not a hearing carried another agent's spend", () => {
      const withSpend = { ...paid, child_spent_usd: 0.0123 };
      const eventHadIt = after(open(), heard(0, withSpend), result([paid]));
      expect(eventHadIt.steps[0]).toMatchObject({ calls: [paid] });
      expect(eventHadIt.spent_usd).toBeCloseTo(0.004, 10);

      const resultHasIt = after(open(), heard(0, paid), result([withSpend]));
      expect(resultHasIt.steps[0]).toMatchObject({ calls: [withSpend] });
      expect(resultHasIt.spent_usd).toBeCloseTo(0.004, 10);
    });

    it("changes nothing for a call whose script has no step here", () => {
      expect(applyRunEvent(run(), heard(0, paid))).toEqual(run());
      const other = after(open("s2"));
      expect(applyRunEvent(other, heard(0, paid))).toEqual(other);
    });

    it("leaves the run it was handed as it was", () => {
      const before = after(open(), heard(0, search));
      const kept = structuredClone(before);
      applyRunEvent(before, heard(1, paid));
      applyRunEvent(before, result([search, paid]));
      expect(before).toEqual(kept);
    });
  });

  it("copies final totals from done/halted and messages from errors and approvals", () => {
    expect(applyRunEvent(run(), { type: "done", spent_usd: 0.5, unknown_cost_calls: 2 })).toMatchObject({ spent_usd: 0.5, unknown_cost_calls: 2 });
    expect(applyRunEvent(run(), { type: "halted", reason: "budget", spent_usd: 1 })).toMatchObject({ summary: "budget", spent_usd: 1 });
    expect(applyRunEvent(run(), { type: "error", message: "kaput" }).summary).toBe("kaput");
    expect(applyRunEvent(run(), { type: "approval_required", approval_id: "a", tool_call_id: "t", name: "write_file", arguments: {}, reason: "", expires_at: "" }).summary).toBe("write_file");
    expect(applyRunEvent(run(), { type: "approval_required", approval_id: "a", tool_call_id: "t", name: "shell_run", arguments: {}, reason: "khớp mẫu cần duyệt: `sudo `", expires_at: "" }).summary).toBe("shell_run (khớp mẫu cần duyệt: `sudo `)");
    expect(applyRunEvent(run(), { type: "text_delta", text: "…" }).steps).toEqual([]);
    expect(applyRunEvent(run(), { type: "model_call", stage: "sent" }).steps).toEqual([]);
  });

  it("takes nothing from the canvas note a message was sent with: it is the sender's stream's alone", () => {
    const midTurn = run({
      summary: "đang làm",
      spent_usd: 0.1,
      steps: [{ kind: "tool", name: "shell_run", ok: null, output: null, duration_ms: null }],
    });
    expect(applyRunEvent(midTurn, { type: "user_context", context: "[Canvas]\n> chạy 5 km" })).toEqual(midTurn);
  });

  it("takes nothing from the pieces of a canvas being written: they are no step of the run", () => {
    const midTurn = run({
      summary: "đang làm",
      spent_usd: 0.1,
      steps: [{ kind: "model", chars: 0, first_token_ms: 300, duration_ms: null }],
    });
    const piece ={ type: "tool_call_delta", index: 0, name: "artifact_create", chunk: '{"title":"Kế', attempt: 0 } as const;
    expect(applyRunEvent(midTurn, piece)).toEqual(midTurn);
  });

  it("labels a paused question by what it asked and leaves its step open, as the server does", () => {
    const asked = applyRunEvent(run(), {
      type: "approval_required",
      approval_id: "a",
      tool_call_id: "t",
      name: "ask_user",
      arguments: { question: "Dời hạn sang thứ sáu?" },
      reason: "",
      expires_at: "",
      kind: "question",
      options: ["có", "không"],
    });
    expect(asked.summary).toBe("Dời hạn sang thứ sáu?");
    expect(asked.steps).toEqual([{ kind: "question", question: "Dời hạn sang thứ sáu?", duration_ms: null }]);
  });

  it("records a route fallback as its own step so a failing route is visible", () => {
    const fell = applyRunEvent(run(), { type: "route_fallback", provider: "openrouter", model: "glm", error: "HTTP 429 from glm" });
    expect(fell.steps).toEqual([{ kind: "fallback", provider: "openrouter", model: "glm", error: "HTTP 429 from glm", duration_ms: null }]);
    expect(fell.spent_usd).toBe(run().spent_usd);
  });
});

describe("activityReducer", () => {
  it("merges snapshot, run and event payloads and keeps live runs over stale recent ones", () => {
    let state = activityReducer(emptyActivity, { type: "payload", payload: { type: "snapshot", runs: [run()] } });
    expect(state.connected).toBe(true);
    state = activityReducer(state, {
      type: "payload",
      payload: { type: "event", run_id: "r1", agent_id: "default", conversation_id: "c1", status: "running", event: { type: "tool_call", tool_call_id: "tc", name: "read_file", arguments: {} } },
    });
    expect(state.runs.r1.steps).toHaveLength(1);
    // The REST list still reports the old snapshot: it must not clobber the live run.
    state = activityReducer(state, { type: "recent", runs: [run({ steps: [] }), run({ id: "r0", status: "done", started_at: "2026-09-19T07:00:00Z" })] });
    expect(state.runs.r1.steps).toHaveLength(1);
    expect(state.runs.r0.status).toBe("done");
    // Unknown run ids in events are ignored rather than invented.
    const same = activityReducer(state, {
      type: "payload",
      payload: { type: "event", run_id: "nope", agent_id: "default", conversation_id: null, status: "running", event: { type: "text_delta", text: "" } },
    });
    expect(same).toBe(state);
    state = activityReducer(state, { type: "payload", payload: { type: "run", run: run({ status: "done", finished_at: "2026-09-19T08:01:00Z" }) } });
    expect(state.runs.r1.status).toBe("done");
    state = activityReducer(state, { type: "connection", connected: false });
    expect(state.connected).toBe(false);
  });

  it("takes a run the list calls settled over a live copy the stream stopped updating", () => {
    // The stream dropped mid-run and the run ended before it came back: no event will ever
    // say so, and the list is the only place that knows.
    let state = activityReducer(emptyActivity, { type: "payload", payload: { type: "snapshot", runs: [run()] } });
    state = activityReducer(state, { type: "recent", runs: [run({ status: "done", finished_at: "2026-09-19T08:01:00Z", summary: "Xong." })] });
    expect(state.runs.r1.status).toBe("done");
    expect(state.runs.r1.summary).toBe("Xong.");
    expect(liveRuns(state)).toEqual([]);
  });

  it("lets the list settle a live pause it reports finished, since a finished run never resumes", () => {
    let state = activityReducer(emptyActivity, { type: "payload", payload: { type: "snapshot", runs: [run({ status: "awaiting_approval" })] } });
    state = activityReducer(state, { type: "recent", runs: [run({ status: "awaiting_approval", summary: "cũ" })] });
    expect(state.runs.r1.summary).toBe("");
    state = activityReducer(state, { type: "recent", runs: [run({ status: "done", finished_at: "2026-09-19T08:05:00Z" })] });
    expect(state.runs.r1.status).toBe("done");
    expect(needsAttention(state)).toEqual([]);
  });

  it("lets go of live runs a later snapshot leaves out, and takes a list's word that a run ended", () => {
    let state = activityReducer(emptyActivity, {
      type: "payload",
      payload: { type: "snapshot", runs: [run(), run({ id: "wait", status: "awaiting_approval" })] },
    });
    state = activityReducer(state, { type: "recent", runs: [run({ id: "old", status: "done" })] });
    // Back from a drop: nothing is live on the server any more.
    state = activityReducer(state, { type: "payload", payload: { type: "snapshot", runs: [] } });
    expect(Object.keys(state.runs)).toEqual(["old"]);

    state = activityReducer(state, { type: "payload", payload: { type: "run", run: run({ id: "r2" }) } });
    state = activityReducer(state, { type: "recent", runs: [run({ id: "r2", status: "halted", finished_at: "2026-09-19T08:02:00Z" })] });
    expect(state.runs.r2.status).toBe("halted");
    expect(liveRuns(state)).toEqual([]);
  });

  it("keeps a run it saw finish finished when a list read before the finish lands after it", () => {
    let state = activityReducer(emptyActivity, { type: "payload", payload: { type: "snapshot", runs: [run()] } });
    state = activityReducer(state, {
      type: "payload",
      payload: { type: "run", run: run({ status: "done", finished_at: "2026-09-19T08:01:00Z", summary: "Xong." }) },
    });
    state = activityReducer(state, { type: "recent", runs: [run()] });
    expect(state.runs.r1.status).toBe("done");
    expect(state.runs.r1.summary).toBe("Xong.");
    expect(liveRuns(state)).toEqual([]);
    // Nor while the stream is down, when the list is otherwise the only word on a run.
    state = activityReducer(state, { type: "connection", connected: false });
    state = activityReducer(state, { type: "recent", runs: [run()] });
    expect(state.runs.r1.status).toBe("done");
  });

  it("takes no list's word that a run is going once the stream has said what is live", () => {
    // The stream names every run that starts after its snapshot: one it has not named was
    // over before the snapshot, and the list saying it runs was read before that.
    let state = activityReducer(emptyActivity, { type: "payload", payload: { type: "snapshot", runs: [] } });
    expect(state.synced).toBe(true);
    state = activityReducer(state, { type: "recent", runs: [run(), run({ id: "old", status: "done" })] });
    expect(Object.keys(state.runs)).toEqual(["old"]);
    // Opened again, the stream has said nothing yet, and while it is down it names nothing
    // at all: the list is the only word on a run started meanwhile.
    state = activityReducer(state, { type: "connection", connected: true });
    expect(state.synced).toBe(false);
    state = activityReducer(state, { type: "connection", connected: false });
    expect(state.synced).toBe(false);
    state = activityReducer(state, { type: "recent", runs: [run()] });
    expect(liveRuns(state).map((r) => r.id)).toEqual(["r1"]);
  });

  it("derives sorted, live, per-conversation and attention views", () => {
    const state = activityReducer(emptyActivity, {
      type: "recent",
      runs: [
        run({ id: "old", status: "done", started_at: "2026-09-19T06:00:00Z" }),
        run({ id: "wait", status: "awaiting_approval", conversation_id: "c2", started_at: "2026-09-19T09:00:00Z" }),
        run({ id: "bad", status: "error", started_at: "2026-09-19T08:30:00Z" }),
        run({ id: "live", status: "running", conversation_id: null, source: "job:coach/brief", started_at: "2026-09-19T10:00:00Z" }),
      ],
    });
    expect(sortedRuns(state).map((r) => r.id)).toEqual(["live", "wait", "bad", "old"]);
    expect(liveRuns(state).map((r) => r.id)).toEqual(["live", "wait"]);
    expect(runsForConversation(state, "c1").map((r) => r.id)).toEqual(["bad", "old"]);
    expect(needsAttention(state).map((r) => r.id)).toEqual(["wait", "bad"]);
  });

  // Start times are whole seconds. Runs that share their start and their end stay in the
  // list's order, and one the stream announces has just started: the newest of them.
  it("keeps runs of the same second in the list's order, behind one it hears start", () => {
    const second = { status: "done" as const, started_at: "2026-09-19T08:00:00Z", finished_at: "2026-09-19T08:00:01Z" };
    let state = activityReducer(emptyActivity, { type: "recent", runs: [run({ id: "b", ...second }), run({ id: "a", ...second })] });
    expect(sortedRuns(state).map((r) => r.id)).toEqual(["b", "a"]);

    state = activityReducer(state, { type: "payload", payload: { type: "run", run: run({ id: "c", started_at: second.started_at }) } });
    state = activityReducer(state, { type: "payload", payload: { type: "run", run: run({ id: "c", ...second }) } });

    expect(sortedRuns(state).map((r) => r.id)).toEqual(["c", "b", "a"]);
    expect(runsForConversation(state, "c1").map((r) => r.id)).toEqual(["c", "b", "a"]);
  });
});

describe("runGroups", () => {
  it("tucks a delegated run under the run that asked for it", () => {
    const parent = run({ id: "p", conversation_id: "c-parent", started_at: "2026-09-19T08:00:00Z" });
    const child = run({
      id: "k",
      conversation_id: "c-child",
      source: "delegate:c-parent",
      started_at: "2026-09-19T08:01:00Z",
    });

    const groups = runGroups([child, parent]);

    expect(groups).toHaveLength(1);
    expect(groups[0].run.id).toBe("p");
    expect(groups[0].children.map((c) => c.id)).toEqual(["k"]);
  });

  it("keeps a child visible when its parent run is not in view", () => {
    const orphan = run({ id: "k", conversation_id: "c-child", source: "delegate:gone" });

    const groups = runGroups([orphan]);

    expect(groups.map((g) => g.run.id)).toEqual(["k"]);
    expect(groups[0].children).toEqual([]);
  });

  // A conversation's stored history holds many turns, and the source only names the
  // conversation. The turn that asked is the one going when the child started: a
  // conversation runs one turn at a time, and the delegate tool starts its child inside one.
  const turn = (id: string, from: string, to: string) =>
    run({ id, status: "done", started_at: `2026-09-19T${from}Z`, finished_at: `2026-09-19T${to}Z` });
  const turns = [turn("t3", "10:00:00", "10:05:00"), turn("t2", "09:00:00", "09:05:00"), turn("t1", "08:00:00", "08:05:00")];
  const kid = run({
    id: "kid",
    conversation_id: "c-kid",
    source: "delegate:c1",
    status: "done",
    started_at: "2026-09-19T09:00:30Z",
    finished_at: "2026-09-19T09:01:30Z",
  });
  const shape = (runs: RunInfo[]) => runGroups(runs).map((g) => [g.run.id, g.children.map((c) => c.id)]);

  it("tucks a delegated run under the one turn of its conversation that asked for it", () => {
    expect(shape([...turns, kid])).toEqual([
      ["t3", []],
      ["t2", ["kid"]],
      ["t1", []],
    ]);
  });

  // A task handed off by a script. The turn that asked has no `delegate` step to hang a
  // child on, only the step of the script, whose calls name the tasks; and a script may
  // have three of them going side by side. The child's source and its start are all the
  // grouping reads, so the children hang under that turn as any other does.
  describe("children a script opened", () => {
    const task = (child: string): NestedToolCall => ({ name: "delegate", arguments: { task: "Soạn thư", agent: "writer" }, ok: true, output: `conversation=${child} status=done spent=$0.0123 steps=7 outcome=done Xong.`, ms: 48_211, cost_usd: null, metered: false, child_spent_usd: 0.0123 });
    const asking = run({
      id: "t2",
      status: "done",
      started_at: "2026-09-19T09:00:00Z",
      finished_at: "2026-09-19T09:05:00Z",
      steps: [{ kind: "tool", name: "tool_script", tool_call_id: "call_7", arguments: { script: "…" }, ok: true, output: "xong", calls: [task("c-a"), task("c-b"), task("c-c")], duration_ms: 52_000 }],
    });
    const opened = (id: string, at: string) =>
      run({ id, conversation_id: `c-${id}`, source: "delegate:c1", status: "done", started_at: `2026-09-19T${at}Z`, finished_at: "2026-09-19T09:01:40Z" });
    const kids = [opened("a", "09:00:12"), opened("b", "09:00:12"), opened("c", "09:00:13")];

    it("hang under the turn whose script asked, which has no step of its own for a hand-off", () => {
      expect(asking.steps.map((step) => step.kind === "tool" && step.name)).toEqual(["tool_script"]);
      expect(shape([turns[0], asking, turns[2], ...kids])).toEqual([
        ["t3", []],
        ["t2", ["a", "b", "c"]],
        ["t1", []],
      ]);
      // However the runs are listed: the children before the turn that asked for them.
      expect(shape([...kids, turns[2], asking, turns[0]])).toEqual([
        ["t3", []],
        ["t2", ["a", "b", "c"]],
        ["t1", []],
      ]);
    });

    it("hang under a turn still going, while the script waits for them", () => {
      const going = { ...asking, status: "running" as const, finished_at: null, steps: [{ ...asking.steps[0], ok: null, output: null, calls: [], duration_ms: null }] };
      const working = kids.map((kid) => ({ ...kid, status: "running" as const, finished_at: null }));
      expect(shape([turns[2], going, ...working])).toEqual([
        ["t2", ["a", "b", "c"]],
        ["t1", []],
      ]);
    });
  });

  it("lets a delegated run stand alone when the turn that asked for it is out of view", () => {
    // The turns either side of it are listed, and neither of them asked for it.
    expect(shape([turns[0], turns[2], kid])).toEqual([
      ["t3", []],
      ["kid", []],
      ["t1", []],
    ]);
  });

  // Timestamps are whole seconds, so a turn that ends and the next that begins can share
  // one, and a child started in it could belong to either.
  const kidAt = (at: string) =>
    run({ id: "kid", conversation_id: "c-kid", source: "delegate:c1", status: "done", started_at: `2026-09-19T${at}Z`, finished_at: `2026-09-19T${at}Z` });

  it("gives a child started in the second two turns share to the later turn, however they are listed", () => {
    const earlier = turn("a", "10:00:00", "10:00:05");
    const later = turn("b", "10:00:05", "10:01:00");
    const grouped = [
      ["b", ["kid"]],
      ["a", []],
    ];

    expect(shape([later, earlier, kidAt("10:00:05")])).toEqual(grouped);
    expect(shape([earlier, later, kidAt("10:00:05")])).toEqual(grouped);
  });

  it("tucks a child started in its turn's last second under that turn", () => {
    expect(shape([turn("t", "10:00:00", "10:00:05"), kidAt("10:00:05")])).toEqual([["t", ["kid"]]]);
  });

  it("keeps runs that share their start and their end in the order given, a lone child included", () => {
    const a = turn("a", "10:00:00", "10:00:01");
    const b = turn("b", "10:00:00", "10:00:01");
    const lone = run({ ...kidAt("10:00:00"), id: "lone", source: "delegate:gone", finished_at: "2026-09-19T10:00:01Z" });

    expect(shape([a, lone, b])).toEqual([["a", []], ["lone", []], ["b", []]]);
    expect(shape([b, lone, a])).toEqual([["b", []], ["lone", []], ["a", []]]);
  });

  it("nests only one level, because a child cannot delegate on", () => {
    const parent = run({ id: "p", conversation_id: "c-parent" });
    const a = run({ id: "a", conversation_id: "c-a", source: "delegate:c-parent" });
    const b = run({ id: "b", conversation_id: "c-b", source: "delegate:c-parent" });

    const groups = runGroups([parent, a, b]);

    expect(groups).toHaveLength(1);
    expect(groups[0].children.map((c) => c.id).sort()).toEqual(["a", "b"]);
  });

  it("reads the parent conversation out of the run source", () => {
    expect(parentConversationId(run({ source: "delegate:c-9" }))).toBe("c-9");
    expect(parentConversationId(run({ source: "chat" }))).toBeNull();
    expect(parentConversationId(run({ source: "job:coach/brief" }))).toBeNull();
  });
});
