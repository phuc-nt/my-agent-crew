import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, coachAgent, coderTemplate, fakeAgent, storedMessage } from "./test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  vitest.stubGlobal("fetch", backend.fetch);
  // The app reads its screen from the address bar, and jsdom keeps one address for the
  // whole file — so without this each test would start wherever the last one navigated.
  window.location.hash = "";
});

const DENIED_TEXT = "Người dùng đã TỪ CHỐI hành động này.";

describe("App", () => {
  it("shows the welcome screen and echo hint when only the fake provider is configured", async () => {
    render(<App />);
    expect(await screen.findByText(vi.welcomeTitleFor("Agent"))).toBeInTheDocument();
    expect(screen.getByText(vi.echoHint)).toBeInTheDocument();
    expect(screen.getByText(vi.noConversations)).toBeInTheDocument();
    expect(screen.getByTestId("welcome-crew")).toHaveTextContent(vi.welcomeNoCrew);
  });

  it("speaks as the master, names the team and installs a template from the crew tab", async () => {
    backend.agents = [fakeAgent, coachAgent];
    backend.templates = [coderTemplate];
    render(<App />);
    await screen.findByText(vi.welcomeTitleFor("Agent"));
    expect(screen.getByTestId("welcome-crew")).toHaveTextContent("HLV sức khoẻ");
    expect(screen.getByText(vi.welcomeDelegateSuggestion("HLV sức khoẻ"))).toBeInTheDocument();

    const chip = screen.getByRole("button", { name: /Đội/ });
    expect(chip).toHaveTextContent(vi.crew.count(1));
    await userEvent.click(chip);
    expect(screen.getByRole("button", { name: vi.crew.tab })).toHaveAttribute("aria-current", "page");
    const crew = screen.getByTestId("crew-list");
    expect(within(crew).getAllByTestId("crew-agent")).toHaveLength(2);
    expect(crew).toHaveTextContent(vi.crew.master);

    await userEvent.click(within(screen.getByTestId("template-list")).getByRole("button", { name: vi.crew.install }));
    expect(await within(screen.getByTestId("manage-screen")).findByRole("status")).toHaveTextContent(vi.crew.installed(["coder"]));
    expect(backend.requests.find((r) => r.method === "POST" && r.path === "/agents/install")?.body).toEqual({ template: "coder" });
    await waitFor(() => expect(within(screen.getByTestId("crew-list")).getAllByTestId("crew-agent")).toHaveLength(3));
    expect(screen.getByTestId("template-list")).toHaveTextContent(vi.crew.alreadyInstalled);

    // Back in the chat, the chip counts the agent that was just installed.
    await userEvent.click(screen.getByRole("button", { name: vi.manage.backToChat }));
    expect(await screen.findByRole("button", { name: /Đội/ })).toHaveTextContent(vi.crew.count(2));
  });

  it("creates a conversation on first send and renders the streamed reply", async () => {
    backend.nextTurn = [
      { type: "text_delta", text: "Xin " },
      { type: "text_delta", text: "chào" },
      { type: "assistant_message", message_id: "a1", content: "Xin chào", tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
      { type: "done", spent_usd: 0.02, unknown_cost_calls: 0 },
    ];
    render(<App />);
    await screen.findByText(vi.welcomeTitleFor("Agent"));
    await userEvent.type(screen.getByRole("textbox"), "hello{Enter}");

    expect(await screen.findByTestId("message-assistant")).toHaveTextContent("Xin chào");
    expect(screen.getByTestId("message-user")).toHaveTextContent("hello");
    expect(backend.conversations.size).toBe(1);
    expect(backend.requests.filter((r) => r.path.endsWith("/messages"))[0].body).toEqual({ text: "hello" });
    expect(screen.getByTestId("budget")).toHaveTextContent("$0.02 / $1.00");
    expect(within(screen.getByRole("navigation")).getByRole("button", { current: "page" })).toHaveTextContent(vi.newConversation);
  });

  it("walks the approval flow: pause, approve, then show the tool result", async () => {
    const created = backend.create({ title: "Việc" });
    backend.nextTurn = [
      { type: "assistant_message", message_id: "a1", content: "", tool_calls: [{ id: "tc1", name: "write_file", arguments: { path: "notes.md" } }], provider: null, model: null, cost_usd: null },
      { type: "approval_required", approval_id: "ap1", tool_call_id: "tc1", name: "write_file", arguments: { path: "notes.md" }, reason: "", expires_at: "2026-09-20T03:10:00Z" },
    ];
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Việc/ }));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Việc");
    await userEvent.type(screen.getByRole("textbox"), "ghi chú{Enter}");

    const bar = await screen.findByRole("alertdialog");
    expect(bar).toHaveTextContent(vi.approvalTitle("write_file"));
    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByTestId("tool-card")).toHaveTextContent(vi.toolAwaiting);

    backend.nextTurn = [
      { type: "tool_result", tool_call_id: "tc1", name: "write_file", ok: true, output: "đã ghi notes.md" },
      { type: "assistant_message", message_id: "a2", content: "Xong.", tool_calls: [], provider: null, model: null, cost_usd: null },
      { type: "done", spent_usd: 0, unknown_cost_calls: 1 },
    ];
    await userEvent.click(within(bar).getByRole("button", { name: vi.approve }));

    expect(await screen.findByText("Xong.")).toBeInTheDocument();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getByTestId("tool-card")).toHaveTextContent(vi.toolDone);
    expect(screen.getByRole("textbox")).toBeEnabled();
    expect(screen.getByTitle(vi.unknownCost(1))).toBeInTheDocument();
    const approval = backend.requests.find((r) => r.path.includes("/approvals/"));
    expect(approval).toMatchObject({ path: `/conversations/${created.id}/approvals/ap1`, body: { approve: true } });
  });

  it("restores a stored history including a denied tool and a pending approval", async () => {
    const c = backend.create({
      title: "Cũ",
      status: "awaiting_approval",
      messages: [
        storedMessage("user", "xoá đi"),
        storedMessage("assistant", "", { tool_calls: [{ id: "tc0", name: "write_file", arguments: {} }] }),
        storedMessage("tool", DENIED_TEXT, { tool_call_id: "tc0" }),
        storedMessage("assistant", "", { tool_calls: [{ id: "tc1", name: "write_file", arguments: { path: "b" } }] }),
      ],
      pending_approval: { id: "ap9", conversation_id: "c", message_id: "m", tool_call_id: "tc1", tool_name: "write_file", arguments: { path: "b" }, status: "pending", created_at: "", expires_at: null, resolved_at: null },
    });
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Cũ/ }));
    const cards = await screen.findAllByTestId("tool-card");
    expect(cards[0]).toHaveTextContent(vi.toolDenied);
    expect(cards[1]).toHaveTextContent(vi.toolAwaiting);
    expect(screen.getByRole("alertdialog")).toHaveTextContent("path=b");
    expect(backend.requests.some((r) => r.path === `/conversations/${c.id}`)).toBe(true);
  });

  it("always-allows a tool from the approval bar, shows it in the header and revokes it", async () => {
    backend.create({
      title: "Luôn",
      status: "awaiting_approval",
      messages: [storedMessage("assistant", "", { tool_calls: [{ id: "tc1", name: "write_file", arguments: { path: "b" } }] })],
      pending_approval: { id: "ap1", conversation_id: "c1", message_id: "m", tool_call_id: "tc1", tool_name: "write_file", arguments: { path: "b" }, status: "pending", created_at: "", expires_at: "2026-09-20T03:10:00Z", resolved_at: null },
    });
    backend.nextTurn = [
      { type: "tool_result", tool_call_id: "tc1", name: "write_file", ok: true, output: "đã ghi b" },
      { type: "assistant_message", message_id: "a2", content: "Xong.", tool_calls: [], provider: null, model: null, cost_usd: null },
      { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
    ];
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Luôn/ }));
    const bar = await screen.findByRole("alertdialog");
    expect(bar).toHaveTextContent(/tự từ chối lúc/);
    await userEvent.click(within(bar).getByRole("button", { name: vi.alwaysAllow }));

    expect(await screen.findByText("Xong.")).toBeInTheDocument();
    const approval = backend.requests.find((r) => r.path.includes("/approvals/"));
    expect(approval).toMatchObject({ path: "/conversations/c1/approvals/ap1", body: { approve: true, always: true } });
    const chips = await screen.findByRole("list", { name: vi.autoApproved });
    expect(chips).toHaveTextContent("write_file");

    await userEvent.click(within(chips).getByRole("button", { name: vi.autoApprovedRevoke("write_file") }));
    await waitFor(() => expect(backend.conversations.get("c1")!.auto_approve).toEqual([]));
    expect(screen.queryByRole("list", { name: vi.autoApproved })).not.toBeInTheDocument();
  });

  it("answers a question the agent asked and resumes the turn", async () => {
    // The whole point of the question card: before it, this row offered only Allow and
    // Refuse, and the server 409s both, so the agent waited out its deadline.
    backend.create({
      title: "Hỏi",
      status: "awaiting_approval",
      messages: [storedMessage("assistant", "", { tool_calls: [{ id: "tq", name: "ask_user", arguments: { question: "Dời hạn sang thứ sáu?" } }] })],
      pending_approval: { id: "aq1", conversation_id: "c1", message_id: "m", tool_call_id: "tq", tool_name: "ask_user", arguments: { question: "Dời hạn sang thứ sáu?" }, status: "pending", created_at: "", expires_at: null, resolved_at: null, kind: "question", options: ["có", "không"] },
    });
    backend.nextTurn = [
      { type: "tool_result", tool_call_id: "tq", name: "ask_user", ok: true, output: "không" },
      { type: "assistant_message", message_id: "a2", content: "Giữ nguyên hạn.", tool_calls: [], provider: null, model: null, cost_usd: null },
      { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
    ];
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Hỏi/ }));
    const card = await screen.findByRole("alertdialog");
    expect(card).toHaveTextContent("Dời hạn sang thứ sáu?");
    expect(within(card).queryByRole("button", { name: vi.approve })).not.toBeInTheDocument();

    await userEvent.click(within(card).getByRole("button", { name: "không" }));

    expect(await screen.findByText("Giữ nguyên hạn.")).toBeInTheDocument();
    expect(backend.lastAnswer).toBe("không");
    const sent = backend.requests.find((r) => r.path.includes("/approvals/"));
    expect(sent).toMatchObject({ path: "/conversations/c1/approvals/aq1/answer", body: { answer: "không" } });
  });

  it("surfaces a halted turn and a 409 conflict as notices", async () => {
    backend.create({ title: "A" });
    backend.nextTurn = [{ type: "halted", reason: "budget", spent_usd: 1 }];
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /^A$/ }));
    await userEvent.type(screen.getByRole("textbox"), "x{Enter}");
    expect(await screen.findByTestId("notice")).toHaveTextContent(vi.haltedBudget);

    backend.conversations.get("c1")!.status = "awaiting_approval";
    await userEvent.type(screen.getByRole("textbox"), "y{Enter}");
    await waitFor(() => expect(screen.getByTestId("notice")).toHaveTextContent(vi.busyConflict));
  });

  it("patches autonomous, skills and title from the header", async () => {
    backend.create({ title: "B" });
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /^B$/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: vi.autonomous }));
    await waitFor(() => expect(backend.conversations.get("c1")!.autonomous).toBe(true));

    await userEvent.click(screen.getByText(/Kỹ năng \(0\)/));
    await userEvent.click(screen.getByRole("checkbox", { name: /writer/ }));
    await waitFor(() => expect(backend.conversations.get("c1")!.skills).toEqual(["writer"]));

    await userEvent.click(within(screen.getByRole("heading", { level: 1 })).getByRole("button"));
    await userEvent.keyboard("Tên mới{Enter}");
    await waitFor(() => expect(backend.conversations.get("c1")!.title).toBe("Tên mới"));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Tên mới");
  });

  it("shows the recap of a conversation and rewrites it on demand", async () => {
    backend.create({ title: "C", summary: "Bản tóm tắt cũ." });
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /^C/ }));
    expect(screen.getAllByText("Bản tóm tắt cũ.").length).toBeGreaterThan(0);

    await userEvent.click(screen.getByRole("button", { name: vi.resummarize }));
    expect(await screen.findAllByText(backend.nextSummary)).toHaveLength(2);
    expect(backend.conversations.get("c1")!.summary).toBe(backend.nextSummary);
    expect(backend.requests.some((r) => r.method === "POST" && r.path === "/conversations/c1/summary")).toBe(true);
  });

  it("says a conversation has no recap yet when none was written", async () => {
    backend.create({ title: "D" });
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /^D$/ }));
    expect(screen.getByText(vi.noSummary)).toBeInTheDocument();
  });

  it("deletes after confirmation and opens the settings drawer without secrets", async () => {
    backend.create({ title: "Xoá tôi" });
    render(<App />);
    await screen.findByRole("button", { name: /Xoá tôi/ });
    vitest.spyOn(window, "confirm").mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: vi.deleteConversation }));
    expect(await screen.findByText(vi.noConversations)).toBeInTheDocument();
    expect(backend.conversations.size).toBe(0);

    await userEvent.click(screen.getByRole("button", { name: /Quản lý/ }));
    await userEvent.click(screen.getByRole("button", { name: vi.settings }));
    const body = screen.getByTestId("manage-screen");
    expect(body).toHaveTextContent("fake:echo");
    expect(body).toHaveTextContent(vi.keyMissing);
    expect(body).toHaveTextContent(vi.requiresApproval);
    expect(body).toHaveTextContent("/tmp/home/workspace");

    // Settings is a place now rather than a layer over the chat, so leaving it is
    // going back rather than dismissing something.
    await userEvent.click(screen.getByRole("button", { name: vi.manage.backToChat }));
    expect(screen.queryByTestId("manage-screen")).not.toBeInTheDocument();
  });

  it("shows the shared user directory in settings", async () => {
    render(<App />);
    await screen.findByText(vi.welcomeTitleFor("Agent"));
    await userEvent.click(screen.getByRole("button", { name: /Quản lý/ }));
    await userEvent.click(screen.getByRole("button", { name: vi.settings }));
    expect(screen.getByTestId("manage-screen")).toHaveTextContent("/tmp/home/users");
  });

  it("opens the memory section and counts the proposals waiting for a decision", async () => {
    backend.addProposal({ description: "Ngủ trước 23h" });
    render(<App />);
    await screen.findByText(vi.welcomeTitleFor("Agent"));

    await userEvent.click(screen.getByRole("button", { name: /Quản lý/ }));
    const link = await screen.findByRole("button", { name: new RegExp(vi.memory.tab) });
    await waitFor(() => expect(link).toHaveTextContent("1"));

    await userEvent.click(link);
    expect(await screen.findByTestId("memory-panel")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: new RegExp(vi.memory.proposals) }));
    expect(await screen.findByText("Ngủ trước 23h")).toBeInTheDocument();
  });
});
