// A desktop action that waits for a person: one line saying what it does, the server's reason
// when it gave one, and the picture the agent chose it on with the point marked and when that
// picture was taken; the raw arguments stay under all of it. The picture is the one the
// conversation's screenshot saved, else the agent's folder, and none where it cannot be had.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { agentFileUrl } from "../api/client";
import { App } from "../app";
import { vi } from "../i18n/vi";
import { FakeBackend, coachAgent, fakeAgent, fakeApproval, fakeRun, storedMessage } from "../test/fake-backend";
import { toolPending } from "../test/pending";
import { ApprovalBar } from "./approval-bar";
import { AttentionCenter } from "./attention-center";
import { formatDateTime } from "./run-timeline";

const F = "00000000000000a1-1456x910-1";
const SHOT_AT = "2026-10-14T02:05:00Z";
const REASON = "ứng dụng Notes chưa có trong danh sách computer_apps của agent";
const CLICK = { kind: "click", app: "Notes", frame_id: F, x: 728, y: 455 };
const savedLine = (path: string) =>
  `Đã chụp màn hình và lưu vào ${path}. frame_id: ${F} (1456×910; toạ độ của computer_act tính theo điểm ảnh của ảnh này).`;

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  backend.agents = [fakeAgent, { ...coachAgent, computer: "on", computer_apps: ["Notes"], write_paths: ["records/kept"] }];
  vitest.stubGlobal("fetch", backend.fetch);
  window.location.hash = "";
});

afterEach(() => {
  vitest.unstubAllGlobals();
});

/** A conversation of `agent` whose screenshot saved the frame, or that took none. */
function conversation(shot: string | null, agent = "coach") {
  const messages = shot
    ? [
        storedMessage("assistant", "", { tool_calls: [{ id: "s1", name: "computer_screenshot", arguments: {} }] }),
        storedMessage("tool", savedLine(shot), { tool_call_id: "s1", name: "computer_screenshot", created_at: SHOT_AT }),
      ]
    : [];
  return backend.create({ agent_id: agent, title: "Ghi chú", messages });
}

const bar = (args: Record<string, unknown>, more: { reason?: string; conversationId?: string } = {}) =>
  render(<ApprovalBar pending={toolPending({ name: "computer_act", arguments: args, ...more })} busy={false} onDecide={() => undefined} conversationId={more.conversationId} />);
const line = (in_: HTMLElement = document.body) => within(in_).queryByTestId("approval-call");
const raw = (in_: HTMLElement = document.body) => in_.querySelector(".approval-text > code") as HTMLElement;
const frame = () => screen.findByTestId("desktop-frame");
const points = () => screen.queryAllByTestId("desktop-frame-point");
const before = (first: Element, second: Element) => Boolean(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING);
const asked = (path: string) => backend.requests.filter((r) => r.method === "GET" && r.path === path).length;

describe("the line of a waiting desktop action", () => {
  it.each([
    [{ kind: "click", ref: "e12", name: "Lưu" }, "Bấm «Lưu» (e12) trong Notes"],
    [{ kind: "double_click", x: 10, y: 20 }, "Bấm đúp tại điểm (10, 20) trong Notes"],
    [{ kind: "right_click", ref: "e3" }, "Bấm chuột phải phần tử e3 trong Notes"],
    [{ kind: "drag", x: 1, y: 2, to_x: 3, to_y: 4 }, "Kéo từ điểm (1, 2) tới điểm (3, 4) trong Notes"],
    [{ kind: "scroll", x: 5, y: 6, dy: 3 }, "Cuộn 0 dòng ngang, 3 dòng dọc tại điểm (5, 6) trong Notes"],
    [{ kind: "type", text: "Mua sữa" }, "Gõ «Mua sữa» vào chỗ đang có con trỏ trong Notes"],
    [{ kind: "set_value", ref: "e7", text: "42" }, "Đặt «42» vào phần tử e7 trong Notes"],
    [{ kind: "key", keys: "cmd+s" }, "Nhấn cmd+s trong Notes"],
    [{ kind: "focus_app" }, "Đưa Notes lên trước màn hình"],
  ])("reads %j as one line, above the raw arguments", (args, said) => {
    bar({ app: "Notes", ...args });

    expect(line()?.textContent).toBe(said);
    expect(before(line() as HTMLElement, raw())).toBe(true);
    expect(raw()).toHaveTextContent(`kind=${args.kind}`);
    expect(screen.getByText(vi.approvalTitle("computer_act"))).toBeInTheDocument();
  });

  it("stands under the server's reason when it gave one", () => {
    bar(CLICK, { reason: REASON });

    const reason = screen.getByText(REASON);
    expect(reason).toHaveClass("approval-reason");
    expect(before(reason, line() as HTMLElement)).toBe(true);
  });

  it("has no reason invented where the server gave none", () => {
    bar(CLICK, { reason: "" });

    expect(document.querySelector(".approval-reason")).toBeNull();
    expect(line()).toBeInTheDocument();
  });
});

describe("the picture a waiting desktop action was chosen on", () => {
  it("is the one the conversation's screenshot saved, with when it was taken", async () => {
    const path = `records/kept/desktop/${F}.png`;
    const chat = conversation(path);
    bar(CLICK, { conversationId: chat.id });

    const shown = await frame();
    const url = agentFileUrl("coach", path);
    expect(within(shown).getByRole("img")).toHaveAttribute("src", url);
    expect(within(shown).getByRole("img")).toHaveAttribute("alt", vi.desktop.frame.alt(1456, 910));
    expect(within(shown).getByRole("link")).toHaveAttribute("href", url);
    expect(screen.getByTestId("desktop-frame-time")).toHaveTextContent(vi.desktop.frame.takenAt(formatDateTime(SHOT_AT)));
    expect(asked("/agents/coach")).toBe(0);
    // Read first in words, then seen, then in full.
    expect(before(line() as HTMLElement, shown)).toBe(true);
    expect(before(shown, raw())).toBe(true);
  });

  it("is the agent's folder where no screenshot of the conversation saved it, and says no time", async () => {
    bar(CLICK, { conversationId: conversation(null).id });

    const shown = await frame();
    expect(within(shown).getByRole("img")).toHaveAttribute("src", agentFileUrl("coach", `records/kept/desktop/${F}.png`));
    expect(screen.queryByTestId("desktop-frame-time")).not.toBeInTheDocument();
    expect(asked("/agents/coach")).toBe(1);
  });

  it("is left out once the picture cannot be loaded, and the card reads as it does without one", async () => {
    bar(CLICK, { conversationId: conversation(`desktop/${F}.png`).id });

    fireEvent.error(within(await frame()).getByRole("img"));

    await waitFor(() => expect(screen.queryByTestId("desktop-frame")).not.toBeInTheDocument());
    expect(line()).toBeInTheDocument();
    expect(raw()).toHaveTextContent(`frame_id=${F}`);
  });

  it.each([
    ["a frame id that is not one", { ...CLICK, frame_id: "../../secrets" }],
    ["no frame id", { kind: "focus_app", app: "Notes" }],
  ])("is not looked for with %s", async (_what, args) => {
    const chat = conversation(`desktop/${F}.png`);
    bar(args, { conversationId: chat.id });
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(screen.queryByTestId("desktop-frame")).not.toBeInTheDocument();
    expect(asked(`/conversations/${chat.id}`)).toBe(0);
  });

  it("is not there for a conversation that cannot be read", async () => {
    bar(CLICK, { conversationId: "gone" });
    await waitFor(() => expect(asked("/conversations/gone")).toBe(1));
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(screen.queryByTestId("desktop-frame")).not.toBeInTheDocument();
    expect(line()).toBeInTheDocument();
  });

  it("marks the point by the picture's size as the frame id names it", async () => {
    bar({ ...CLICK, frame_id: "00000000000000a1-1000x500-1", x: 250, y: 400 }, { conversationId: conversation(null).id });
    const shown = await frame();

    // The box the marks sit in takes the picture's shape from the id too.
    expect(within(shown).getByRole("link").style.getPropertyValue("--frame-ratio")).toBe("2");
    expect(points()).toHaveLength(1);
    expect(points()[0]).toHaveStyle({ left: "25%", top: "80%" });
    expect(points()[0]).toHaveAttribute("title", vi.desktop.frame.point);
  });

  it("marks both ends of a drag, the second as where it drops", async () => {
    bar({ ...CLICK, kind: "drag", x: 0, y: 910, to_x: 1456, to_y: 0 }, { conversationId: conversation(null).id });
    await frame();

    expect(points().map((p) => [p.style.left, p.style.top, p.classList.contains("drop")])).toEqual([
      ["0%", "100%", false],
      ["100%", "0%", true],
    ]);
    expect(points()[1]).toHaveAttribute("title", vi.desktop.frame.dropPoint);
  });

  it.each([
    ["an action on an element", { ...CLICK, ref: "e12" }],
    ["a point off the picture", { ...CLICK, x: 1457 }],
    ["a kind that names no point", { kind: "key", app: "Notes", frame_id: F, keys: "return" }],
  ])("marks no point for %s, and still shows the picture", async (_what, args) => {
    bar(args, { conversationId: conversation(null).id });
    await frame();

    expect(points()).toHaveLength(0);
  });

  it("is never the last frame's while the next call's frame is looked for", async () => {
    const next = "00000000000000b2-1456x910-1";
    const chat = conversation(`desktop/${F}.png`);
    const view = bar(CLICK, { conversationId: chat.id });
    expect(within(await frame()).getByRole("img")).toHaveAttribute("src", agentFileUrl("coach", `desktop/${F}.png`));

    // The next read of the conversation is answered, but its answer is held on the way back.
    const real = backend.fetch;
    let release = () => {};
    let held = false;
    vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      const answer = await real(input, init);
      if (!held) {
        held = true;
        await new Promise<void>((resolve) => {
          release = resolve;
        });
      }
      return answer;
    });
    view.rerender(
      <ApprovalBar pending={toolPending({ name: "computer_act", arguments: { ...CLICK, frame_id: next } })} busy={false} onDecide={() => undefined} conversationId={chat.id} />,
    );
    await waitFor(() => expect(asked(`/conversations/${chat.id}`)).toBe(2));
    expect(screen.queryByTestId("desktop-frame")).not.toBeInTheDocument();

    await act(async () => release());
    await waitFor(() => expect(within(screen.getByTestId("desktop-frame")).getByRole("img")).toHaveAttribute("src", agentFileUrl("coach", `records/kept/desktop/${next}.png`)));
  });

  it("is not looked for beside another tool's call", async () => {
    const chat = conversation(`desktop/${F}.png`);
    render(<ApprovalBar pending={toolPending({ name: "write_file", arguments: { frame_id: F } })} busy={false} onDecide={() => undefined} conversationId={chat.id} />);
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(screen.queryByTestId("desktop-frame")).not.toBeInTheDocument();
    expect(asked(`/conversations/${chat.id}`)).toBe(0);
  });
});

describe("a desktop action waiting where a person decides", () => {
  const pending = { tool_call_id: "a1", tool_name: "computer_act", arguments: CLICK, status: "pending" as const, resolved_at: null };

  it("shows its picture in the bar of the conversation it waits in", async () => {
    // The master's, so the chat lists it as it opens.
    const chat = conversation(`desktop/${F}.png`, "default");
    chat.title = "Thao tác";
    chat.status = "awaiting_approval";
    chat.messages.push(storedMessage("assistant", "", { tool_calls: [{ id: "a1", name: "computer_act", arguments: CLICK }] }));
    chat.pending_approval = fakeApproval({ ...pending, id: "ap1", expires_at: null });
    render(<App />);

    await userEvent.click(await screen.findByRole("button", { name: /Thao tác/ }));

    const dialog = await screen.findByRole("alertdialog", { name: vi.awaitingApproval });
    expect(line(dialog)).toHaveTextContent(/^Bấm tại điểm \(728, 455\) trong Notes$/);
    const shown = await within(dialog).findByTestId("desktop-frame");
    expect(within(shown).getByRole("img")).toHaveAttribute("src", agentFileUrl("default", `desktop/${F}.png`));
  });

  it("shows its picture in its row of the list of requests", async () => {
    const chat = conversation(`desktop/${F}.png`);
    chat.status = "awaiting_approval";
    chat.pending_approval = fakeApproval({ ...pending, id: "ap2", expires_at: new Date(Date.now() + 300_000).toISOString() });
    const run = fakeRun({ id: "run-1", agent_id: "coach", status: "awaiting_approval", finished_at: null, conversation_id: chat.id });
    render(<AttentionCenter runs={[run]} inline agentName={() => "Coach"} onOpenConversation={() => undefined} onReload={() => undefined} />);

    const row = await screen.findByRole("group", { name: new RegExp(`^${vi.attentionAwaiting("Coach")}`) });
    const shown = await within(row).findByTestId("desktop-frame");
    expect(within(shown).getByRole("img")).toHaveAttribute("src", agentFileUrl("coach", `desktop/${F}.png`));
    expect(within(row).getByTestId("desktop-frame-time")).toHaveTextContent(formatDateTime(SHOT_AT));
  });
});
