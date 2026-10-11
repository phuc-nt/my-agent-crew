import { describe, expect, it } from "vitest";
import type { NestedToolCall } from "../api/types";
import { notYetListed, storedWork, withNested, workOf } from "./nested-calls";

function call(overrides: Partial<NestedToolCall> = {}): NestedToolCall {
  return {
    name: "workspace_read",
    arguments: { path: "a.md" },
    ok: true,
    output: "hai dòng",
    ms: 4,
    cost_usd: null,
    metered: false,
    ...overrides,
  };
}

const search = call({ name: "mcp__notion__search", arguments: { query: "kế hoạch" }, output: "3 trang", ms: 120 });
const paid = call({ name: "pdf_read", output: "Tổng chi 4,2 triệu.", ms: 1_500, cost_usd: 0.004, metered: true });

describe("the calls of a result that were not listed while the script ran", () => {
  it("are all of them when none was listed", () => {
    expect(notYetListed([], [search, paid])).toEqual([search, paid]);
  });

  it("are none when each was heard as it ended, in whatever order that was", () => {
    expect(notYetListed([paid, search], [search, paid])).toEqual([]);
  });

  it("are the ones no event came for, in the order the result names them", () => {
    const third = call({ arguments: { path: "b.md" } });
    expect(notYetListed([paid], [search, paid, third])).toEqual([search, third]);
  });

  // A script may read the same file twice: one heard answers for one of the two.
  it("count a call made twice as two, of which one listed leaves one", () => {
    const again = call();
    expect(notYetListed([call()], [call(), again])).toEqual([again]);
    expect(notYetListed([call(), call()], [call(), again])).toEqual([]);
  });

  it.each<[string, Partial<NestedToolCall>]>([
    ["name", { name: "workspace_list" }],
    ["arguments", { arguments: { path: "b.md" } }],
    ["outcome", { ok: false }],
    ["answer", { output: "ba dòng" }],
    ["duration", { ms: 5 }],
    ["price", { cost_usd: 0.001 }],
    ["being charged", { metered: true }],
  ])("take a call for another when its %s differs", (_what, change) => {
    const other = call(change);
    expect(notYetListed([call()], [other])).toEqual([other]);
  });

  it("leave both lists as they were handed in", () => {
    const listed = [search];
    const calls = [search, paid];
    notYetListed(listed, calls);
    expect(listed).toEqual([search]);
    expect(calls).toEqual([search, paid]);
  });
});

describe("a script's calls with one more heard", () => {
  it("grow by the call when it is the next the script made, from no list at all too", () => {
    expect(withNested(undefined, 0, search)).toEqual({ calls: [search], added: true });
    expect(withNested([search], 1, paid)).toEqual({ calls: [search, paid], added: true });
  });

  it("keep their length when the call is one already heard, and say it is not new", () => {
    const heard = withNested([search, paid], 1, paid);
    expect(heard).toEqual({ calls: [search, paid], added: false });
    // What was heard last is what is kept, in the place the script made it.
    expect(withNested([search, paid], 0, paid)).toEqual({ calls: [paid, paid], added: false });
  });

  it("take a call whose place is past the end as new, and put it last", () => {
    expect(withNested([search], 5, paid)).toEqual({ calls: [search, paid], added: true });
  });

  it("are a new list each time: the one handed in is the state being read", () => {
    const before = [search];
    const { calls } = withNested(before, 1, paid);
    expect(before).toEqual([search]);
    expect(calls).not.toBe(before);
    expect(withNested(before, 0, paid).calls).not.toBe(before);
    expect(before).toEqual([search]);
  });
});

describe("what a result says of a script's work", () => {
  it("is the calls and the two measures of a script that made some", () => {
    expect(workOf({ calls: [search], received_chars: 1_200, printed_chars: 80 })).toEqual({
      calls: [search],
      received_chars: 1_200,
      printed_chars: 80,
    });
  });

  it("has no list for a tool that called nothing, sent empty or not sent", () => {
    expect(workOf({ calls: [] })).toEqual({});
    expect(workOf({})).toEqual({});
  });

  // Nought is a count: a script that called nothing was handed nothing, and says so.
  it("keeps a measure of nought and drops one nobody counted", () => {
    expect(workOf({ calls: [], received_chars: 0, printed_chars: 0 })).toEqual({ received_chars: 0, printed_chars: 0 });
    expect(workOf({ received_chars: null, printed_chars: null })).toEqual({});
    expect(workOf({ received_chars: null, printed_chars: 8 })).toEqual({ printed_chars: 8 });
    expect(workOf({ received_chars: 12, printed_chars: null })).toEqual({ received_chars: 12 });
  });
});

describe("what a stored result kept beside its output", () => {
  const kept = (value: unknown) => JSON.stringify(value);

  it("is read back as the server wrote it", () => {
    const context = kept({ calls: [search, paid], received_chars: 26, printed_chars: 8 });
    expect(storedWork(context)).toEqual({ calls: [search, paid], received_chars: 26, printed_chars: 8 });
  });

  it("is the measures alone for a script that called nothing", () => {
    expect(storedWork(kept({ calls: [], received_chars: 0, printed_chars: 8 }))).toEqual({ received_chars: 0, printed_chars: 8 });
  });

  it("is the calls alone for a result stored with no measure", () => {
    expect(storedWork(kept({ calls: [search], received_chars: null, printed_chars: null }))).toEqual({ calls: [search] });
  });

  it("is nothing for a result that kept nothing", () => {
    expect(storedWork("")).toEqual({});
    expect(storedWork(undefined)).toEqual({});
  });

  // The field holds a person's canvas note on another kind of message.
  it.each([
    "[Canvas · Kế hoạch tuần]\n> chạy 5 km",
    '{"calls": [',
    "null",
    "3",
    '"calls"',
    "true",
    "[]",
  ])("is nothing, and no error, for a row that is not one: %j", (context) => {
    expect(storedWork(context)).toEqual({});
  });

  it.each<[string, unknown]>([
    ["no list at all", "mcp__notion__search"],
    ["a mapping", { 0: search }],
    ["null", null],
  ])("lists no calls when what stands for them is %s, and still reads the measures", (_what, calls) => {
    expect(storedWork(kept({ calls, received_chars: 26, printed_chars: 8 }))).toEqual({ received_chars: 26, printed_chars: 8 });
  });

  it.each<[string, unknown]>([
    ["is no object", "workspace_read"],
    ["is null", null],
    ["has no name", { ...search, name: undefined }],
    ["has arguments that are no mapping", { ...search, arguments: "query=kế hoạch" }],
    ["has no arguments", { ...search, arguments: null }],
    ["has an outcome that is no yes or no", { ...search, ok: "true" }],
    ["has an answer that is no text", { ...search, output: null }],
    ["has a duration that is no number", { ...search, ms: "120" }],
    ["has a price that is neither a number nor unknown", { ...search, cost_usd: "0.004" }],
    ["has no word on being charged", { ...search, metered: undefined }],
  ])("lists none of the calls when one of them %s: half a list would read as the whole", (_what, broken) => {
    const context = kept({ calls: [search, broken, paid], received_chars: 26, printed_chars: 8 });
    expect(storedWork(context)).toEqual({ received_chars: 26, printed_chars: 8 });
  });

  it("reads a measure only when it is a number", () => {
    expect(storedWork(kept({ calls: [search], received_chars: "26", printed_chars: true }))).toEqual({ calls: [search] });
  });
});
