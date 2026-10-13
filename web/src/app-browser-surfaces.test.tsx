// The browser's surfaces as the app hands them what they need: the crew's names to the
// machine's card, the machine's state to an agent's setting without reading it again, a tab's
// conversation to the chat, the agent of a conversation or a run to its screenshot, and the
// catalogue to the tools grid. On a server older than all of it, none of them is drawn.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentInfo } from "./api/types";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, FakeEventSource, coachAgent, fakeAgent, fakeApproval, fakeRun, storedMessage } from "./test/fake-backend";
import { BROWSER_ACT_TOOL, BROWSER_READ_TOOLS, browserMachine, browserTab } from "./test/fake-browser";

const PATH = "screenshots/20261013T120000Z-don.png";
const SHOT = `Đã lưu ảnh chụp tab don vào ${PATH}.\nKích thước 1280x720, 48 KB.`;
const coach = (rest: Partial<AgentInfo> = {}): AgentInfo => ({ ...coachAgent, browser: "act", browser_hosts: ["shop.example"], ...rest });

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  backend.agents = [fakeAgent, coach()];
  backend.browser.machine = browserMachine({ enabled: true });
  FakeEventSource.instances = [];
  vitest.stubGlobal("fetch", backend.fetch);
  vitest.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vitest.unstubAllGlobals();
  window.location.hash = "";
});

const open = (hash: string) => {
  window.location.hash = hash;
  render(<App />);
};
const asked = (path: string, method = "GET") => backend.requests.filter((r) => r.method === method && r.path === path).length;
const section = () => within(screen.getByTestId("section-tools"));

describe("the browser on the connections page", () => {
  it("names whose browser is up by the names the crew goes by", async () => {
    backend.browser.start("coach", [browserTab()]);
    open("#/manage/connections");

    const card = within(await screen.findByTestId("browser-machine"));
    expect(card.getByRole("heading", { name: vi.browser.title })).toBeInTheDocument();
    expect(card.getByTestId("browser-machine-state")).toHaveTextContent("Đang bật");
    expect(card.getByTestId("browser-machine-running")).toHaveTextContent(/^Đang chạy cho 1 agent: HLV sức khoẻ$/);
    // The card shows and sets nothing.
    expect(card.queryByRole("button")).not.toBeInTheDocument();
    expect(card.queryByRole("checkbox")).not.toBeInTheDocument();
  });
});

describe("the browser on an agent's page", () => {
  it("warns of a machine that gives no browser from the connections already read, asking for them once", async () => {
    backend.browser.machine = browserMachine({ enabled: false });
    open("#/manage/crew/coach");

    await screen.findByTestId("agent-editor");
    expect(await section().findByTestId("browser-machine-warning")).toBeInTheDocument();
    expect(section().getByRole("combobox", { name: vi.browser.mode })).toHaveValue("act");
    expect(section().getByRole("textbox", { name: vi.browser.hosts })).toHaveValue("shop.example");
    // The card under the form is read from the agent's own route.
    expect(await screen.findByTestId("browser-state")).toHaveTextContent(vi.browser.card.machineOff);
    expect(asked("/connections")).toBe(1);
    expect(asked("/agents/coach/browser")).toBeGreaterThanOrEqual(1);
  });

  it("has no warning on a machine that has a browser to start", async () => {
    open("#/manage/crew/coach");

    expect(await screen.findByTestId("browser-state")).toHaveTextContent(vi.browser.card.stopped);
    expect(section().queryByTestId("browser-machine-warning")).not.toBeInTheDocument();
  });

  it("leads from a tab to the conversation it belongs to", async () => {
    const chat = backend.create({ title: "Giỏ hàng", agent_id: "coach" });
    backend.browser.start("coach", [browserTab({ id: 3, label: "gio", conversation_id: chat.id })]);
    open("#/manage/crew/coach");

    const card = within(await screen.findByTestId("browser-card"));
    await userEvent.click(await card.findByRole("button", { name: vi.browser.card.conversationOf("gio") }));

    await waitFor(() => expect(window.location.hash).toBe(`#/chat/${chat.id}`));
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Giỏ hàng");
  });

  it("stops the browser at once when a save sets the agent back to off, and the card goes", async () => {
    backend.browser.start("coach", [browserTab()]);
    open("#/manage/crew/coach");
    expect(await screen.findByTestId("browser-state")).toHaveTextContent(vi.browser.card.running(1));

    await userEvent.selectOptions(section().getByRole("combobox", { name: vi.browser.mode }), "off");
    await userEvent.click(screen.getByRole("button", { name: vi.editor.save }));

    await waitFor(() => expect(screen.queryByTestId("browser-card")).not.toBeInTheDocument());
    expect(backend.requests.filter((r) => r.method === "PATCH").map((r) => (r.body as { profile: object }).profile)).toEqual([{ browser: "off" }]);
    expect(backend.browser.running("coach")).toBe(false);
    // The page stopped nothing itself: the save did.
    expect(asked("/agents/coach/browser/stop", "POST")).toBe(0);
  });
});

describe("the browser's tools on the tools page", () => {
  it("are the rows the server lists, each marked as coming with the browser", async () => {
    open("#/manage/tools");

    await waitFor(() => expect(screen.getAllByText(vi.browser.withBrowser)).toHaveLength(6));
    const rows = screen.getAllByTestId("tool-row");
    for (const name of [...BROWSER_READ_TOOLS, BROWSER_ACT_TOOL]) {
      const row = rows.find((r) => within(r).queryByText(name)) as HTMLElement;
      expect(within(row).getByText(vi.browser.withBrowser)).toHaveAttribute("title", vi.browser.withBrowserTitle);
      // Columns: the approval cell, then the master, who has no browser, and the coach.
      expect(within(row).getAllByRole("cell")[1]).toHaveClass("browser-off");
      expect(within(within(row).getAllByRole("cell")[2]).getByText("✓")).toBeInTheDocument();
    }
  });
});

describe("a screenshot's picture", () => {
  it("is asked of the agent the conversation belongs to", async () => {
    const chat = backend.create({
      title: "Chụp đơn",
      agent_id: "coach",
      messages: [
        storedMessage("user", "chụp trang đơn hàng"),
        storedMessage("assistant", "", { tool_calls: [{ id: "tc1", name: "browser_screenshot", arguments: { tab: "don" } }] }),
        storedMessage("tool", SHOT, { tool_call_id: "tc1" }),
      ],
    });
    open(`#/chat/${chat.id}`);

    const card = within(await screen.findByTestId("tool-card"));
    const link = card.getByRole("link", { name: "Ảnh chụp tab don" });
    expect(link).toHaveAttribute("href", `/api/agents/coach/files?path=${encodeURIComponent(PATH)}`);
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("is asked of the agent that ran, on the page of one run", async () => {
    backend.runs = [
      fakeRun({
        id: "r7",
        agent_id: "coach",
        steps: [{ kind: "tool", name: "browser_screenshot", tool_call_id: "tc1", arguments: { tab: "don" }, ok: true, output: SHOT.replace(/\s+/g, " "), duration_ms: 420 }],
      }),
    ];
    open("#/manage/activity/r7");

    const step = within(await screen.findByTestId("run-step"));
    expect(step.getByRole("link", { name: "Ảnh chụp tab don" })).toHaveAttribute("href", `/api/agents/coach/files?path=${encodeURIComponent(PATH)}`);
  });
});

describe("a browser call waiting on the approvals page", () => {
  it("is said in one line in its row", async () => {
    const pending_approval = fakeApproval({
      status: "pending",
      resolved_at: null,
      expires_at: new Date(Date.now() + 5 * 60_000).toISOString(),
      tool_name: "browser_act",
      arguments: { kind: "click", ref: "e12", name: "Thanh toán" },
      agent_id: "coach",
    });
    const chat = backend.create({ title: "Giỏ hàng", agent_id: "coach", status: "awaiting_approval", pending_approval });
    backend.runs = [fakeRun({ id: "r8", agent_id: "coach", status: "awaiting_approval", finished_at: null, conversation_id: chat.id })];
    open("#/manage/approvals");

    expect(await screen.findByTestId("approval-call")).toHaveTextContent(/^Bấm «Thanh toán»$/);
  });
});

describe("the app on a server older than the browser", () => {
  beforeEach(() => {
    backend.browser.old = true;
    backend.agents = backend.agents.map(({ browser: _mode, browser_hosts: _hosts, ...agent }) => agent);
  });

  it("has no browser card among the connections", async () => {
    open("#/manage/connections");

    await screen.findByTestId("providers");
    expect(screen.getByTestId("connections")).toBeInTheDocument();
    expect(screen.queryByTestId("browser-machine")).not.toBeInTheDocument();
    expect(screen.queryByText(vi.browser.title)).not.toBeInTheDocument();
  });

  it("has no setting and no card on an agent's page, which opens whole and clean", async () => {
    open("#/manage/crew/coach");

    await screen.findByTestId("agent-editor");
    await waitFor(() => expect(asked("/agents/coach/browser")).toBe(1));
    expect(section().queryByRole("combobox", { name: vi.browser.mode })).not.toBeInTheDocument();
    expect(screen.queryByTestId("browser-card")).not.toBeInTheDocument();
    expect(screen.queryByText(vi.browser.title)).not.toBeInTheDocument();
    expect(screen.getByText(vi.editor.clean)).toBeInTheDocument();
  });

  it("has no browser row, mark or legend line on the tools page", async () => {
    open("#/manage/tools");

    await screen.findAllByTestId("tool-row");
    expect(screen.queryByText(vi.browser.withBrowser)).not.toBeInTheDocument();
    expect(screen.queryByText(/^browser_/)).not.toBeInTheDocument();
    expect(screen.queryByText(vi.browser.cellOff)).not.toBeInTheDocument();
  });
});
