import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import type { AgentEvent, NestedToolCall } from "../../api/types";
import { vi } from "../../i18n/vi";
import { emptyThread, itemsFromMessages, threadReducer, type ThreadItem, type ToolStatus } from "../../state/thread-reducer";
import { storedMessage } from "../../test/fake-backend";
import { MessageThread } from "../message-thread";
import { ToolCallCard } from "../tool-call-card";
import type { CanvasLinks } from "./canvas-card";

type Tool = Extract<ThreadItem, { kind: "tool" }>;

const LETTER = "9c2f41ab07de";
const MENU = "0123456789ab";
const TITLES: Record<string, string> = { [LETTER]: "Thư trả lời", [MENU]: "Thực đơn" };
const { card } = vi.canvas;

/** A write a script made, as the server lists it: let through the gate, and its canvas's tag
 *  whole at the head of what is otherwise a cut line. */
function wrote(name: string, args: Record<string, unknown>, output: string, ok = true): NestedToolCall {
  return { name, arguments: args, ok, output, ms: 21, cost_usd: null, metered: false, gated: true };
}
const created = wrote("artifact_create", { title: "Thư trả lời", kind: "markdown", content: "Kính gửi anh Minh…" }, `[artifact ${LETTER} v1] Đã tạo canvas "Thư trả lời" (markdown).`);
const edited = wrote("artifact_edit", { id: LETTER, old_text: "anh Minh", new_text: "anh Minh," }, `[artifact ${LETTER} v2] Đã sửa.`);
const same = wrote("artifact_edit", { id: LETTER, old_text: "anh", new_text: "anh" }, `[artifact ${LETTER} v2 unchanged] Không có gì đổi.`);
const rewritten = wrote("artifact_rewrite", { id: LETTER, content: "Kính gửi…" }, `[artifact ${LETTER} v3] Đã viết lại.`);
const imported = wrote("artifact_import", { path: "thuc-don.md" }, `[artifact ${MENU} v1] Đã nhập "Thực đơn".`);
const read: NestedToolCall = { name: "workspace_read", arguments: { path: "thu.md" }, ok: true, output: "Kính gửi", ms: 4, cost_usd: null, metered: false };

const script = { id: "s1", name: "tool_script", arguments: { script: "artifact_create(title='Thư trả lời', content=thu)" } };
function ran(calls: NestedToolCall[], status: ToolStatus = "done"): Tool {
  return { kind: "tool", ...script, output: status === "running" ? null : "xong", status, calls };
}

function links() {
  return {
    titleOf: vitest.fn((id: string) => TITLES[id] ?? null),
    isGone: vitest.fn(() => false),
    verify: vitest.fn(),
    open: vitest.fn(),
  } satisfies CanvasLinks;
}

/** The canvas cards on screen: the write each stands for, and what each says. */
const cards = () => screen.queryAllByTestId("canvas-card");
const said = () => cards().map((it) => [it.getAttribute("data-tool"), it.querySelector(".canvas-card-title")?.textContent, it.querySelector(".canvas-card-line")?.textContent]);

describe("the canvases a script wrote, in the thread", () => {
  it("each have their card under the script's, as a write the agent made itself has", () => {
    const canvas = links();
    render(<ToolCallCard item={ran([read, created, edited, same, rewritten, imported])} canvas={canvas} />);

    expect(said()).toEqual([
      ["artifact_create", "Thư trả lời", card.version(card.created, 1)],
      ["artifact_edit", "Thư trả lời", card.version(card.edited, 2)],
      ["artifact_edit", "Thư trả lời", card.version(card.unchanged, 2)],
      ["artifact_rewrite", "Thư trả lời", card.version(card.rewritten, 3)],
      ["artifact_import", "Thực đơn", card.version(card.imported, 1)],
    ]);
    // The script keeps its own card, with every call it made still listed in it; the canvas
    // cards stand beside that card and not inside the list it folds away.
    const own = screen.getByTestId("tool-card");
    expect(own).toHaveAttribute("data-tool", "tool_script");
    expect(within(own).getAllByTestId("script-call")).toHaveLength(6);
    for (const it of cards()) expect(own.contains(it)).toBe(false);
    expect(own.compareDocumentPosition(cards()[0]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("each open the canvas their own tag names", () => {
    const canvas = links();
    render(<ToolCallCard item={ran([created, imported])} canvas={canvas} />);

    fireEvent.click(screen.getByRole("button", { name: card.openLabel("Thực đơn") }));
    fireEvent.click(screen.getByRole("button", { name: card.openLabel("Thư trả lời") }));

    expect(canvas.open.mock.calls).toEqual([[MENU], [LETTER]]);
    // Each is asked about once, as the card of a direct write asks.
    expect(canvas.verify.mock.calls).toEqual([[LETTER], [MENU]]);
  });

  it("say a canvas deleted since is gone, and offer nothing to open", () => {
    const canvas = { ...links(), isGone: vitest.fn((id: string) => id === LETTER) };
    render(<ToolCallCard item={ran([created, imported])} canvas={canvas} />);

    expect(said().map(([, , line]) => line)).toEqual([vi.canvas.gone, card.version(card.imported, 1)]);
    expect(screen.queryByRole("button", { name: card.openLabel("Thư trả lời") })).toBeNull();
  });

  it("are none for a write that failed, which stays a row of the script's list saying so", () => {
    const failed = wrote("artifact_edit", { id: LETTER, old_text: "chị", new_text: "anh" }, "old_text not found", false);
    render(<ToolCallCard item={ran([failed])} canvas={links()} />);

    expect(cards()).toEqual([]);
    expect(screen.getByTestId("script-call")).toHaveTextContent(vi.toolFailed);
  });

  it("are none for what a script only read, wrote out to a file or handed off", () => {
    const others: NestedToolCall[] = [
      { ...read, name: "artifact_read", arguments: { id: LETTER }, output: `[artifact ${LETTER} v1] Kính gửi` },
      { ...read, name: "artifact_list", arguments: {}, output: `${LETTER} Thư trả lời` },
      wrote("artifact_export", { id: LETTER, path: "out/thu.md" }, "Đã ghi out/thu.md"),
      { ...read, name: "delegate", arguments: { task: "Soạn thư" }, output: `conversation=3f9a1c0b7d2e status=done spent=$0.0123 steps=7 outcome=done [artifact ${LETTER} v1] Thư trả lời` },
    ];
    render(<ToolCallCard item={ran(others)} canvas={links()} />);

    expect(cards()).toEqual([]);
    expect(screen.getAllByTestId("script-call")).toHaveLength(4);
  });

  it("are not drawn where the thread was given no way to open a canvas", () => {
    render(<ToolCallCard item={ran([created])} />);

    expect(cards()).toEqual([]);
    expect(screen.getByTestId("tool-card")).toHaveAttribute("data-tool", "tool_script");
  });

  it("are there as soon as each write is heard of, finished, while the script still runs", () => {
    const say = (events: AgentEvent[]) =>
      events.reduce((state, event) => threadReducer(state, { type: "event", event }), { ...emptyThread, busy: true });
    const opening: AgentEvent[] = [
      { type: "assistant_message", message_id: "a", content: "", tool_calls: [script], provider: null, model: null, cost_usd: null },
      { type: "tool_call", tool_call_id: "s1", name: "tool_script", arguments: script.arguments },
    ];
    const canvas = links();
    const view = render(<ToolCallCard item={say(opening).items[0] as Tool} canvas={canvas} />);
    expect(cards()).toEqual([]);

    const heard = say([...opening, { type: "nested_call", tool_call_id: "s1", index: 0, call: created }]).items[0] as Tool;
    expect(heard.status).toBe("running");
    view.rerender(<ToolCallCard item={heard} canvas={canvas} />);

    // A script's call is heard of once it has ended: its card never says it is still writing.
    expect(said()).toEqual([["artifact_create", "Thư trả lời", card.version(card.created, 1)]]);
    expect(screen.getByRole("button", { name: card.openLabel("Thư trả lời") })).toBeInTheDocument();
  });

  it.each<ToolStatus>(["failed", "stopped"])("stay for a script that %s after it wrote, since the canvas is there", (status) => {
    render(<ToolCallCard item={ran([created], status)} canvas={links()} />);

    expect(said()).toEqual([["artifact_create", "Thư trả lời", card.version(card.created, 1)]]);
    expect(screen.getByTestId("tool-card")).toHaveAttribute("data-tool", "tool_script");
  });

  it("are one for each time a script made the very same call", () => {
    render(<ToolCallCard item={ran([same, same])} canvas={links()} />);

    expect(said()).toEqual([
      ["artifact_edit", "Thư trả lời", card.version(card.unchanged, 2)],
      ["artifact_edit", "Thư trả lời", card.version(card.unchanged, 2)],
    ]);
  });
});

describe("the canvases a script wrote, in a conversation read from the server", () => {
  const user: ThreadItem = { kind: "user", id: "m1", text: "soạn thư trả lời" };
  const kept = JSON.stringify({ calls: [read, created, imported], received_chars: 120, printed_chars: 4 });
  const stored = itemsFromMessages([
    storedMessage("assistant", "", { tool_calls: [script, { id: "t2", name: "web_search", arguments: { query: "hoá đơn" } }] }),
    storedMessage("tool", "xong", { tool_call_id: "s1", context: kept }),
    storedMessage("tool", "…", { tool_call_id: "t2" }),
  ]);

  function thread(canvas?: CanvasLinks) {
    return render(
      <MessageThread items={[user, ...stored]} streaming={null} busy={false} onSuggestion={() => {}} echoOnly={false} agentId="master" canvas={canvas} />,
    );
  }

  it("still have their cards, right after the script's and before the turn's next call", () => {
    thread(links());

    expect(screen.getAllByTestId(/^(tool-card|canvas-card)$/).map((it) => it.getAttribute("data-tool"))).toEqual([
      "tool_script",
      "artifact_create",
      "artifact_import",
      "web_search",
    ]);
  });

  it("open from their cards, through the links the thread was given", () => {
    const canvas = links();
    thread(canvas);

    fireEvent.click(screen.getByRole("button", { name: card.openLabel("Thư trả lời") }));

    expect(canvas.open).toHaveBeenCalledExactlyOnceWith(LETTER);
  });

  it("are not drawn in a thread that was given no links", () => {
    thread();

    expect(cards()).toEqual([]);
  });
});
