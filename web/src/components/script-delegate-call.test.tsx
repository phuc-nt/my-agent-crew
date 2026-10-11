import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentEvent, Conversation, NestedToolCall } from "../api/types";
import { vi } from "../i18n/vi";
import { conversationMarkdown } from "../lib/conversation-markdown";
import { scriptCallsMarkdown } from "../lib/script-calls-markdown";
import { runGroups } from "../state/activity-reducer";
import { emptyThread, itemsFromMessages, threadReducer, type ThreadItem } from "../state/thread-reducer";
import { FakeBackend, fakeRun, storedMessage } from "../test/fake-backend";
import { memoryStorage } from "../test/memory-storage";
import { ConversationList } from "./conversation-list";
import { RunCard, RunGroupCard } from "./run-timeline";
import { ScriptCalls } from "./script-calls";
import { ToolCallCard } from "./tool-call-card";

type Tool = Extract<ThreadItem, { kind: "tool" }>;

/**
 * A task a script handed to another agent, as the server lists it: the other agent's whole
 * answer cut to one line, what it spent apart from any price of the call itself, and no
 * price of its own, since the money was the other conversation's.
 */
function task(child: string, spent: number | null = 0.0123): NestedToolCall {
  return {
    name: "delegate",
    arguments: { task: "Soạn thư trả lời khách về hoá đơn tháng 10", agent: "writer" },
    ok: true,
    output: `conversation=${child} status=done spent=$0.0123 steps=7 outcome=done Thư đã soạn xong: Kính gửi anh Minh, …`,
    ms: 48_211,
    cost_usd: null,
    metered: false,
    ...(spent === null ? {} : { child_spent_usd: spent }),
  };
}
const CHILD = "3f9a1c0b7d2e";
const handedOff = task(CHILD);
const read: NestedToolCall = { name: "workspace_read", arguments: { path: "thu.md" }, ok: true, output: "Kính gửi", ms: 4, cost_usd: null, metered: false };
/** Refused before any conversation was opened: there is nothing spent and nowhere to go. */
const refused: NestedToolCall = { ...task(CHILD, null), ok: false, output: "agent 'writer' không nhận việc từ agent này", ms: 3 };

const SPENT = vi.scriptCallChildSpent("$0.0123");
const script = { id: "call_7", name: "tool_script", arguments: { script: "delegate('Soạn thư trả lời khách', agent='writer')" } };
const kept = (calls: unknown) => JSON.stringify({ calls, received_chars: 140, printed_chars: 12 });

/** Each listed call: what it says the other agent spent, and whether it offers the way in. */
function listed(inside: HTMLElement) {
  const rows = within(inside).getAllByTestId("script-call");
  return {
    rows,
    spent: rows.map((row) => within(row).queryByTestId("script-call-child-spent")?.textContent ?? null),
    ways: rows.map((row) => within(row).queryByRole("button", { name: vi.delegateOpenChild }) !== null),
  };
}

describe("a task a script handed to another agent", () => {
  it("says what the other agent spent, as the card of a task handed off directly does, and prices no call", () => {
    render(<ScriptCalls calls={[read, handedOff, refused]} />);
    const { rows, spent } = listed(screen.getByTestId("script-calls"));

    expect(spent).toEqual([null, SPENT, null]);
    // The other conversation's money, to the four places its own card writes it in.
    expect(SPENT).toContain("$0.0123");
    // Not what this script's call paid: the line that says that stays off the row.
    expect(within(rows[1]).queryByTestId("script-call-cost")).toBeNull();
    expect(rows[1].querySelector("code.script-call-name")).toHaveTextContent("delegate");
    expect(within(rows[1]).getByTestId("script-call-output")).toHaveTextContent("Thư đã soạn xong");
    expect(rows[2]).toHaveTextContent(vi.toolFailed);
  });

  it.each([
    ["nothing", null],
    ["nought", 0],
  ])("says nothing of spending where the other agent spent %s", (_, spent) => {
    render(<ScriptCalls calls={[task(CHILD, spent)]} />);

    expect(listed(screen.getByTestId("script-calls")).spent).toEqual([null]);
  });

  it("opens the conversation the task ran in, read from the head of its answer", async () => {
    const open = vitest.fn();
    render(<ScriptCalls calls={[read, handedOff, refused, task("77aa00bb11cc", null)]} onOpenConversation={open} />);
    const { rows, ways } = listed(screen.getByTestId("script-calls"));

    // One that opened no conversation offers none; one that spent nothing still does.
    expect(ways).toEqual([false, true, false, true]);
    await userEvent.click(within(rows[1]).getByRole("button", { name: vi.delegateOpenChild }));
    await userEvent.click(within(rows[3]).getByRole("button", { name: vi.delegateOpenChild }));
    expect(open.mock.calls).toEqual([[CHILD], ["77aa00bb11cc"]]);
  });

  it("offers no way in where the list was given none to offer", () => {
    render(<ScriptCalls calls={[handedOff]} />);

    expect(listed(screen.getByTestId("script-calls"))).toMatchObject({ spent: [SPENT], ways: [false] });
  });

  it("reads the same on the chat card while the script runs, once it has ended and read back from the store", async () => {
    const say = (events: AgentEvent[]) =>
      events.reduce((state, event) => threadReducer(state, { type: "event", event }), { ...emptyThread, busy: true });
    const opening: AgentEvent[] = [
      { type: "assistant_message", message_id: "a", content: "", tool_calls: [script], provider: null, model: null, cost_usd: null },
      { type: "tool_call", tool_call_id: "call_7", name: "tool_script", arguments: script.arguments },
      { type: "nested_call", tool_call_id: "call_7", index: 0, call: handedOff },
    ];
    const ended: AgentEvent = { type: "tool_result", tool_call_id: "call_7", name: "tool_script", ok: true, output: "đã giao", calls: [handedOff], received_chars: 140, printed_chars: 12 };
    const [stored] = itemsFromMessages([
      storedMessage("assistant", "", { tool_calls: [script] }),
      storedMessage("tool", "đã giao", { tool_call_id: "call_7", context: kept([handedOff]) }),
    ]);
    expect(stored).toMatchObject({ calls: [handedOff] });

    for (const item of [say(opening).items[0], say([...opening, ended]).items[0], stored]) {
      const open = vitest.fn();
      const { unmount } = render(<ToolCallCard item={item as Tool} onOpenConversation={open} />);
      const { rows, spent } = listed(screen.getByTestId("tool-card"));

      expect(spent).toEqual([SPENT]);
      await userEvent.click(within(rows[0]).getByRole("button", { name: vi.delegateOpenChild }));
      expect(open).toHaveBeenCalledExactlyOnceWith(CHILD);
      unmount();
    }
  });

  it("is written in the exported conversation with what the other agent spent, said in words", () => {
    const line = `1. \`delegate\` · ${vi.stepDuration(48_211)} · ${SPENT}`;
    expect(scriptCallsMarkdown([handedOff])).toBe(`${vi.scriptCalls(1, 0)}:\n\n${line}`);
    // The bare figure would read as what the call cost, which is the one thing it is not.
    expect(line).not.toMatch(/· \$\d/);

    const exported = conversationMarkdown(
      new FakeBackend().create({
        title: "Thư khách",
        messages: [
          storedMessage("user", "Trả lời thư này", { created_at: "2026-09-24T23:30:00Z" }),
          storedMessage("assistant", "", { created_at: "2026-09-24T23:30:05Z", tool_calls: [script] }),
          storedMessage("tool", "đã giao", { created_at: "2026-09-24T23:31:00Z", tool_call_id: "call_7", context: kept([handedOff]) }),
        ],
      }),
      "Coach",
    );
    expect(exported).toContain(`\n\n${line}\n`);
  });
});

describe("in Hoạt động, the tasks a script handed off", () => {
  const children = ["3f9a1c0b7d2e", "aa11bb22cc33", "dd44ee55ff66"];
  const asking = fakeRun({
    id: "r-ask",
    conversation_id: "c1",
    started_at: "2026-09-19T08:00:00Z",
    finished_at: "2026-09-19T08:01:00Z",
    spent_usd: 0.004,
    steps: [
      { kind: "tool", name: "tool_script", tool_call_id: "call_7", arguments: script.arguments, ok: true, output: "đã giao ba việc", calls: children.map((child) => task(child)), duration_ms: 52_000 },
    ],
  });
  const opened = children.map((child, n) =>
    fakeRun({ id: `r-kid-${n}`, agent_id: "writer", conversation_id: child, source: "delegate:c1", title: `Soạn thư ${n + 1}`, started_at: "2026-09-19T08:00:12Z", finished_at: "2026-09-19T08:00:50Z", spent_usd: 0.0123 }),
  );

  it("say on the script's step what each of the others spent, and leave the run's own spend alone", () => {
    render(<RunCard run={asking} agentName="Trợ lý" expanded />);
    const steps = screen.getAllByTestId("run-step");

    // The hand-offs have no step of their own: the script's step is where they are listed.
    expect(steps).toHaveLength(1);
    expect(steps[0]).not.toHaveTextContent(vi.stepDelegate);
    expect(listed(steps[0]).spent).toEqual([SPENT, SPENT, SPENT]);
    // What the run itself spent, and not that plus what three other conversations did.
    expect(screen.getByTestId("run-card").querySelector(".run-meta")).toHaveTextContent("$0.0040");
    expect(screen.getByTestId("run-card").querySelector(".run-meta")).not.toHaveTextContent("$0.04");
  });

  it("hang under the turn that asked, three side by side, each call opening the conversation its own task ran in", async () => {
    const open = vitest.fn();
    const groups = runGroups([asking, ...opened]);
    expect(groups).toHaveLength(1);
    render(<RunGroupCard group={groups[0]} agentName={(id) => (id === "writer" ? "Thư ký" : "Trợ lý")} expanded onOpenConversation={open} />);

    const under = within(screen.getByTestId("run-children")).getAllByTestId("run-card");
    expect(under.map((kid) => kid.querySelector(".run-title")?.textContent)).toEqual(["Thư ký · Soạn thư 1", "Thư ký · Soạn thư 2", "Thư ký · Soạn thư 3"]);

    const { rows, ways } = listed(screen.getAllByTestId("run-step")[0]);
    expect(ways).toEqual([true, true, true]);
    await userEvent.click(within(rows[2]).getByRole("button", { name: vi.delegateOpenChild }));
    expect(open).toHaveBeenCalledExactlyOnceWith(children[2]);
  });
});

// A conversation a script opened is tied to a call that is none of its parent's: the id of
// the script's call and the place of the hand-off among the script's calls. The list reads
// only whether there is such a tie, so it shows these as it shows any other agent's work.
describe("in the conversation list, the conversations a script opened", () => {
  const NOW = "2026-09-26T05:00:00Z";
  const conversation = (id: string, updated_at: string, parent_call_id = ""): Conversation => ({
    id,
    agent_id: "default",
    title: id,
    status: "idle",
    channel: "",
    created_at: "2026-09-20T01:00:00Z",
    updated_at,
    autonomous: false,
    cost_cap_usd: 1,
    spent_usd: 0,
    unknown_cost_calls: 0,
    over_budget: false,
    summary: "",
    skills: [],
    auto_approve: [],
    parent_call_id,
  });
  const list = (conversations: Conversation[]) => (
    <ConversationList conversations={conversations} activeId="mine" onSelect={() => {}} onCreate={() => {}} onDelete={() => {}} />
  );
  const titles = () => [...document.querySelectorAll(".conversation-title")].map((title) => title.textContent);
  const marked = () => screen.queryAllByTestId("child-marker").map((mark) => mark.closest("li")?.querySelector(".conversation-title")?.textContent);

  afterEach(() => {
    vitest.useRealTimers();
    vitest.unstubAllGlobals();
  });

  it("are marked as another agent's work, kept below the person's own and never said to be unread", () => {
    vitest.useFakeTimers({ toFake: ["Date"] });
    vitest.setSystemTime(new Date(NOW));
    memoryStorage();
    const mine = conversation("mine", "2026-09-26T03:00:00Z");
    const other = conversation("other", "2026-09-26T02:00:00Z");
    const view = render(list([mine, other]));

    // All three land after the person's own rows were last seen, and newer than both.
    const kids = [0, 1, 2].map((n) => conversation(`kid-${n}`, `2026-09-26T04:0${n}:00Z`, `call_7:${n}`));
    view.rerender(list([kids[2], kids[1], kids[0], mine, other]));

    expect(titles()).toEqual(["mine", "other", "kid-2", "kid-1", "kid-0"]);
    expect(marked()).toEqual(["kid-2", "kid-1", "kid-0"]);
    expect(screen.getAllByTestId("child-marker")[0]).toHaveAttribute("title", vi.delegateChild);
    expect(screen.queryAllByTestId("unread-dot")).toEqual([]);
  });

  it("read exactly as one opened by a task handed off directly", () => {
    vitest.useFakeTimers({ toFake: ["Date"] });
    vitest.setSystemTime(new Date(NOW));
    memoryStorage();
    const row = (parent_call_id: string) => {
      const { unmount } = render(list([conversation("mine", "2026-09-26T03:00:00Z"), conversation("kid", "2026-09-26T04:00:00Z", parent_call_id)]));
      const html = screen.getByText("kid", { selector: ".conversation-title" }).closest("li")?.outerHTML;
      unmount();
      return html;
    };

    const direct = row("call_7");
    expect(direct).toContain("child-marker");
    expect(row("call_7:2")).toBe(direct);
  });
});
