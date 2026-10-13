// A browser call that waits for a person is said in one line above its raw arguments: in the
// chat where the turn paused, and in the list of requests of the manage screen alike.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { ApprovalInfo } from "../api/types";
import { App } from "../app";
import { vi } from "../i18n/vi";
import { FakeBackend, fakeApproval, fakeRun, storedMessage } from "../test/fake-backend";
import { toolPending } from "../test/pending";
import type { PendingApproval } from "../state/thread-reducer";
import { ApprovalBar } from "./approval-bar";
import { AttentionCenter } from "./attention-center";

const REASON = "máy chủ shop.example chưa có trong danh sách của agent";
const CART = { url: "https://shop.example/cart?item=1", tab: "main" };
const PAY = { kind: "click", ref: "e12", name: "Thanh toán", tab: "main" };

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  vitest.stubGlobal("fetch", backend.fetch);
  window.location.hash = "";
});

afterEach(() => {
  vitest.unstubAllGlobals();
});

const bar = (pending: Partial<PendingApproval>) =>
  render(<ApprovalBar pending={toolPending(pending)} busy={false} onDecide={() => undefined} />);
const line = (within_: HTMLElement = document.body) => within(within_).queryByTestId("approval-call");
/** The arguments as they were always shown: one `key=value` line. */
const raw = (within_: HTMLElement = document.body) => within_.querySelector(".approval-text > code") as HTMLElement;
const before = (first: Element, second: Element) =>
  Boolean(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING);

describe("the line of a waiting browser call", () => {
  it("says which page a navigation opens, by its host and not its whole address", () => {
    bar({ name: "browser_navigate", arguments: CART });

    expect(line()).toHaveTextContent(/^Mở trang shop\.example$/);
  });

  it.each([
    [{ kind: "click", name: "Thanh toán" }, "Bấm «Thanh toán»"],
    [{ kind: "fill", name: "Email", text: "a@b.example" }, "Điền «a@b.example» vào «Email»"],
    [{ kind: "press", name: "Tìm kiếm", key: "Enter" }, "Nhấn Enter tại «Tìm kiếm»"],
    [{ kind: "upload", name: "Hoá đơn", path: "inbox/bill.pdf" }, "Tải tệp inbox/bill.pdf lên «Hoá đơn»"],
  ])("says what an action does to which element: %j", (args, said) => {
    bar({ name: "browser_act", arguments: { ref: "e3", ...args } });

    expect(line()?.textContent).toBe(said);
  });

  it.each([
    [{ name: "Tải hoá đơn" }, "Bấm «Tải hoá đơn» để tải tệp về", "ref=e7, name=Tải hoá đơn"],
    [{ name: "Tải hoá đơn", save_as: "hoa-don-10.pdf" }, "Bấm «Tải hoá đơn» để tải tệp về, lưu thành hoa-don-10.pdf", "ref=e7, name=Tải hoá đơn, save_as=hoa-don-10.pdf"],
  ])("says what a download presses, and the name its file is kept under: %j", (args, said, shown) => {
    bar({ name: "browser_download", arguments: { ref: "e7", ...args } });

    expect(line()?.textContent).toBe(said);
    expect(raw()).toHaveTextContent(shown);
    expect(before(line() as HTMLElement, raw())).toBe(true);
    expect(screen.getByText(vi.approvalTitle("browser_download"))).toBeInTheDocument();
  });

  it("stands under the title and the server's reason, and above the raw arguments", () => {
    bar({ name: "browser_navigate", arguments: CART, reason: REASON });

    const said = line() as HTMLElement;
    const reason = screen.getByText(REASON);
    expect(reason).toHaveClass("approval-reason");
    expect(before(screen.getByText(vi.approvalTitle("browser_navigate")), reason)).toBe(true);
    expect(before(reason, said)).toBe(true);
    expect(before(said, raw())).toBe(true);
  });

  it("leaves the raw arguments under it as they were shown before", () => {
    bar({ name: "browser_act", arguments: PAY });

    expect(raw()).toHaveTextContent("kind=click, ref=e12, name=Thanh toán, tab=main");
    expect(line()).not.toHaveTextContent("e12");
  });

  it("is there without a reason, and the reason without it", () => {
    const { unmount } = bar({ name: "browser_act", arguments: PAY });
    expect(line()).toBeInTheDocument();
    expect(document.querySelector(".approval-reason")).toBeNull();
    unmount();

    bar({ name: "shell_run", arguments: { command: "rm -rf out" }, reason: REASON });
    expect(screen.getByText(REASON)).toBeInTheDocument();
    expect(line()).not.toBeInTheDocument();
  });

  it.each([
    ["another tool, whatever its arguments are called", "write_file", { url: "https://shop.example", kind: "click", name: "x" }],
    ["a browser tool that asks nobody", "browser_text", { tab: "main" }],
    ["a navigation that names no address", "browser_navigate", { tab: "main" }],
    ["an action that names no element", "browser_act", { kind: "click", ref: "e12" }],
    ["an action of a kind not known here", "browser_act", { kind: "drag", name: "Thẻ" }],
    ["a download that names no element", "browser_download", { ref: "e7", save_as: "hoa-don.pdf" }],
    ["a page saved as a file, which asks nobody", "browser_pdf", { tab: "main", name: "Tải" }],
  ])("is not there for %s, and the raw arguments still are", (_what, name, args) => {
    bar({ name, arguments: args });

    expect(line()).not.toBeInTheDocument();
    expect(raw().textContent).not.toBe("—");
    expect(screen.getByText(vi.approvalTitle(name))).toBeInTheDocument();
  });
});

describe("a browser call waiting in the chat", () => {
  it("is said in the bar of a conversation opened on a stored request", async () => {
    backend.create({
      title: "Giỏ hàng",
      status: "awaiting_approval",
      messages: [storedMessage("assistant", "", { tool_calls: [{ id: "tc1", name: "browser_act", arguments: PAY }] })],
      pending_approval: fakeApproval({ id: "ap9", tool_call_id: "tc1", tool_name: "browser_act", arguments: PAY, status: "pending", resolved_at: null, expires_at: null }),
    });
    render(<App />);

    await userEvent.click(await screen.findByRole("button", { name: /Giỏ hàng/ }));

    const dialog = await screen.findByRole("alertdialog", { name: vi.awaitingApproval });
    expect(line(dialog)).toHaveTextContent(/^Bấm «Thanh toán»$/);
    expect(before(line(dialog) as HTMLElement, raw(dialog))).toBe(true);
    expect(raw(dialog)).toHaveTextContent("kind=click");
  });

  it("is said, under the server's reason, in the bar of a turn that pauses while it streams", async () => {
    backend.create({ title: "Mua" });
    backend.nextTurn = [
      { type: "assistant_message", message_id: "a1", content: "", tool_calls: [{ id: "tc1", name: "browser_navigate", arguments: CART }], provider: null, model: null, cost_usd: null },
      { type: "approval_required", approval_id: "ap1", tool_call_id: "tc1", name: "browser_navigate", arguments: CART, reason: REASON, expires_at: "2026-09-20T03:10:00Z" },
    ];
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Mua/ }));

    await userEvent.type(screen.getByRole("textbox"), "mở giỏ hàng{Enter}");

    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent(vi.approvalTitle("browser_navigate"));
    expect(line(dialog)).toHaveTextContent(/^Mở trang shop\.example$/);
    const reason = within(dialog).getByText(REASON);
    expect(before(reason, line(dialog) as HTMLElement)).toBe(true);
    // A reason cannot be waived, so the bar offers no "always allow" beside the line.
    expect(within(dialog).queryByRole("button", { name: vi.alwaysAllow })).not.toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: vi.approve })).toBeEnabled();
  });

  it("is not said for another tool's call", async () => {
    backend.create({
      title: "Sổ tay",
      status: "awaiting_approval",
      messages: [storedMessage("assistant", "", { tool_calls: [{ id: "tc1", name: "write_file", arguments: { path: "b" } }] })],
      pending_approval: fakeApproval({ id: "ap9", tool_call_id: "tc1", tool_name: "write_file", arguments: { path: "b" }, status: "pending", resolved_at: null, expires_at: null }),
    });
    render(<App />);

    await userEvent.click(await screen.findByRole("button", { name: /Sổ tay/ }));

    const dialog = await screen.findByRole("alertdialog");
    expect(raw(dialog)).toHaveTextContent("path=b");
    expect(line(dialog)).not.toBeInTheDocument();
  });
});

describe("a browser call waiting in the list of requests", () => {
  const inFiveMinutes = () => new Date(Date.now() + 5 * 60_000).toISOString();

  /** A conversation paused on `approval`, listed as the manage screen lists what waits. */
  function listed(approval: Partial<ApprovalInfo>) {
    const pending_approval = fakeApproval({ status: "pending", resolved_at: null, expires_at: inFiveMinutes(), ...approval });
    const conversation = backend.create({ status: "awaiting_approval", pending_approval });
    const run = fakeRun({ id: `run-${conversation.id}`, status: "awaiting_approval", finished_at: null, conversation_id: conversation.id });
    render(<AttentionCenter runs={[run]} inline agentName={() => "Agent"} onOpenConversation={() => undefined} onReload={() => undefined} />);
    return screen.findByRole("group", { name: new RegExp(`^${vi.attentionAwaiting("Agent")}`) });
  }

  it("is said in its row, under the reason the server gave and above the raw arguments", async () => {
    const row = await listed({ tool_name: "browser_navigate", arguments: CART, reason: REASON });

    const said = line(row) as HTMLElement;
    expect(said).toHaveTextContent(/^Mở trang shop\.example$/);
    expect(before(within(row).getByText(REASON), said)).toBe(true);
    expect(before(said, raw(row))).toBe(true);
    expect(raw(row)).toHaveTextContent("url=https://shop.example/cart?item=1");
    // The row still counts its time down and still takes the decision.
    expect(within(row).getByRole("timer")).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: vi.approve })).toBeEnabled();
  });

  it("says an action the same way", async () => {
    const row = await listed({ tool_name: "browser_act", arguments: { kind: "type", ref: "e4", name: "Mã giảm giá", text: "TET26" } });

    expect(line(row)?.textContent).toBe("Gõ «TET26» vào «Mã giảm giá»");
  });

  it("says a download the same way, above the arguments it was read from", async () => {
    const row = await listed({ tool_name: "browser_download", arguments: { ref: "e7", name: "Xuất sao kê", save_as: "sao-ke.csv" } });

    expect(line(row)?.textContent).toBe("Bấm «Xuất sao kê» để tải tệp về, lưu thành sao-ke.csv");
    expect(before(line(row) as HTMLElement, raw(row))).toBe(true);
    expect(raw(row)).toHaveTextContent("save_as=sao-ke.csv");
  });

  it("is not said for another tool's request", async () => {
    const row = await listed({ tool_name: "shell_run", arguments: { command: "rm -rf out" }, reason: REASON });

    expect(row).toHaveTextContent("command=rm -rf out");
    expect(line(row)).not.toBeInTheDocument();
  });
});
