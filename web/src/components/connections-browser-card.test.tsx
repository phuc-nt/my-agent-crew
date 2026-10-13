// The machine's browser on the connections page: one card that sets nothing and says whether
// the crew may start a browser, which one, what is missing, and whose is up. That last line
// changes with nobody on the page doing anything, so the card reads it again by itself.
import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as mock } from "vitest";
import type { BrowserConnection, ConnectionsInfo, CredentialsInfo } from "../api/types";
import { BROWSER_POLL_MS } from "../hooks/use-agent-browser";
import type { CredentialsController } from "../hooks/use-credentials";
import type { McpController } from "../hooks/use-mcp-servers";
import { vi } from "../i18n/vi";
import { FakeBackend, coachAgent, fakeAgent } from "../test/fake-backend";
import { browserMachine } from "../test/fake-browser";
import { ConnectionsPanel } from "./connections-panel";

const t = vi.browser.machine;

const base: ConnectionsInfo = {
  providers: [],
  routes: [],
  routes_source: "config",
  vision_routes: [],
  audio_routes: [],
  keys: [],
  search_backends: ["duckduckgo"],
  firecrawl_base_url: "",
  telegram: [],
};

const info: CredentialsInfo = { file: "/h/env", items: [], restart_required: null };
const credentials: CredentialsController = {
  info,
  error: null,
  save: mock.fn(async () => info),
  remove: mock.fn(async () => info),
  check: mock.fn(async () => ({ ok: true, detail: "" })),
};
const nothing = async () => undefined;
const mcp: McpController = { servers: [], error: null, refresh: nothing, keysChanged: nothing, crewChanged: nothing, reconnect: nothing, signIn: nothing, signOut: nothing };

const NAMES: Record<string, string> = { coach: "HLV sức khoẻ", purchases: "Thủ kho" };
const named = (id: string) => NAMES[id] ?? id;

let backend: FakeBackend;
/** Set by a test whose server stops answering. */
let down = false;

beforeEach(() => {
  backend = new FakeBackend();
  backend.agents = [fakeAgent, coachAgent, { ...coachAgent, id: "purchases", name: "Thủ kho" }];
  down = false;
  mock.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    if (down) throw new TypeError("Failed to fetch");
    return backend.fetch(input, init);
  });
});

afterEach(() => {
  mock.useRealTimers();
  mock.restoreAllMocks();
  mock.unstubAllGlobals();
});

/** The page as the server's answer draws it, on a machine that says `machine` of its browser.
 *  The server goes on saying the same, unless `really` names whose browser is up by now. */
function show(machine: Partial<BrowserConnection> | null, agentName?: (id: string) => string, really?: string[]) {
  const browser = { ...browserMachine(), running: [], ...machine };
  const { running, ...rest } = browser;
  backend.browser.old = machine === null;
  backend.browser.machine = rest;
  for (const id of really ?? running) backend.browser.start(id);
  const connections = machine === null ? base : { ...base, browser };
  return render(<ConnectionsPanel connections={connections} credentials={credentials} mcp={mcp} agentName={agentName} onChanged={() => undefined} />);
}

const asked = () => backend.requests.filter((r) => r.method === "GET" && r.path === "/connections").length;
/** Lets every answer on its way land, and what it draws be drawn. */
const settle = () => act(() => new Promise<void>((resolve) => setTimeout(resolve, 0)));
/** Only the page's own clock is the test's to turn; the waits of the test itself stay real. */
const clock = () => mock.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
async function pass(ms: number) {
  act(() => {
    mock.advanceTimersByTime(ms);
  });
  await settle();
}
/** The page is looked at again, or looked away from: the browser says which. */
const look = () =>
  act(() => {
    document.dispatchEvent(new Event("visibilitychange"));
  });

const card = () => within(screen.getByTestId("browser-machine"));
const state = () => screen.getByTestId("browser-machine-state");
const running = () => screen.getByTestId("browser-machine-running");

describe("the browser card of the connections page", () => {
  it("is not drawn for a server that says nothing of a browser, and the rest of the page is", () => {
    show(null);

    expect(screen.queryByTestId("browser-machine")).not.toBeInTheDocument();
    expect(screen.queryByText(vi.browser.title)).not.toBeInTheDocument();
    expect(screen.getByTestId("providers")).toBeInTheDocument();
  });

  it("is named, and says a switched-off browser is off and where the switch is", () => {
    show({ enabled: false });

    expect(card().getByText(vi.browser.title)).toBeInTheDocument();
    expect(state()).toHaveTextContent(t.off);
    expect(t.off).toContain("browser_enabled: true");
    expect(t.off).toContain("config.yaml");
    // A browser that is off is not said to be the crew's or the machine's, nor a version.
    expect(state()).not.toHaveTextContent(t.channel.chromium);
    expect(state()).not.toHaveTextContent("141.0.7390.37");
    expect(screen.queryByTestId("browser-missing")).not.toBeInTheDocument();
  });

  it("says a switched-on browser is on, that it is the crew's own Chromium, and its version", () => {
    show({ enabled: true, channel: "chromium", version: "141.0.7390.37" });

    expect(within(state()).getByText(t.on)).toHaveClass("badge", "ok");
    expect(state()).toHaveTextContent("Chromium của đội");
    expect(state()).toHaveTextContent("141.0.7390.37");
    expect(state()).not.toHaveTextContent(t.off);
    expect(screen.queryByTestId("browser-missing")).not.toBeInTheDocument();
  });

  it("says the machine's own Chrome where the machine's file asks for that one", () => {
    show({ enabled: true, channel: "chrome", version: "141.0.7390.55" });

    expect(state()).toHaveTextContent("Chrome của máy");
    expect(state()).not.toHaveTextContent("Chromium của đội");
    expect(state()).toHaveTextContent("141.0.7390.55");
  });

  it("leaves the version out when the server has none to say", () => {
    show({ enabled: true, version: "" });

    expect(state().children).toHaveLength(2);
    expect(state()).toHaveTextContent(/^Đang bậtChromium của đội$/);
  });

  it("says the playwright package is missing, with the command that installs it", () => {
    show({ enabled: true, installed: false, version: "", missing: "playwright", install_command: "uv sync --extra browser" });

    const missing = screen.getByTestId("browser-missing");
    expect(missing).toHaveTextContent(t.missingPlaywright);
    expect(missing).toHaveTextContent(t.installWith);
    expect(within(missing).getByText("uv sync --extra browser").tagName).toBe("CODE");
    expect(missing).toHaveClass("warn-text");
  });

  it("says Chromium is not installed, with the command that installs it", () => {
    show({ enabled: true, installed: false, version: "", missing: "browser", install_command: "uv run playwright install chromium" });

    const missing = screen.getByTestId("browser-missing");
    expect(missing).toHaveTextContent(t.missingChromium);
    expect(missing).not.toHaveTextContent(t.missingChrome);
    expect(within(missing).getByText("uv run playwright install chromium").tagName).toBe("CODE");
  });

  it("says the machine has no Chrome when a browser is missing and there is no command to give", () => {
    show({ enabled: true, channel: "chrome", installed: false, version: "", missing: "browser", install_command: "" });

    const missing = screen.getByTestId("browser-missing");
    expect(missing).toHaveTextContent(t.missingChrome);
    expect(t.missingChrome).toContain("Google Chrome");
    expect(missing).not.toHaveTextContent(t.missingChromium);
    expect(missing).not.toHaveTextContent(t.installWith);
    expect(missing.querySelector("code")).toBeNull();
  });

  it("says what is missing on a machine with the browser switched off as well", () => {
    show({ enabled: false, installed: false, version: "", missing: "browser", install_command: "uv run playwright install chromium" });

    expect(state()).toHaveTextContent(t.off);
    expect(screen.getByTestId("browser-missing")).toHaveTextContent(t.missingChromium);
  });

  it("names the agents whose browser is up by the names the page knows them by", () => {
    show({ enabled: true, running: ["coach", "purchases"] }, (id) => NAMES[id] ?? id);

    expect(running()).toHaveTextContent("Đang chạy cho 2 agent: HLV sức khoẻ, Thủ kho");
  });

  it("names them by id where the page has no name to give", () => {
    show({ enabled: true, running: ["coach", "purchases"] });

    expect(running()).toHaveTextContent("Đang chạy cho 2 agent: coach, purchases");
  });

  it("counts one as one", () => {
    show({ enabled: true, running: ["coach"] }, (id) => NAMES[id] ?? id);

    expect(running()).toHaveTextContent(/^Đang chạy cho 1 agent: HLV sức khoẻ$/);
  });

  it("says nobody has a browser open while none is up", () => {
    show({ enabled: true, running: [] });

    expect(running()).toHaveTextContent(/^Chưa agent nào đang mở trình duyệt\.$/);
  });

  it("has nothing to press, type in or follow: the switch is the machine's own file", () => {
    show({ enabled: true, installed: false, missing: "browser", install_command: "uv run playwright install chromium", running: ["coach"] });

    for (const role of ["button", "link", "textbox", "checkbox", "combobox", "switch"]) expect(card().queryAllByRole(role)).toHaveLength(0);
  });
});

describe("whose browser is up, on a page nobody reloads", () => {
  const NOBODY = /^Chưa agent nào đang mở trình duyệt\.$/;

  it("is read as the card is drawn, however long ago the page's own answer came", async () => {
    // The page read the machine before the coach's first call brought its browser up.
    show({ enabled: true, running: [] }, named, ["coach"]);
    expect(running()).toHaveTextContent(NOBODY);

    await settle();

    expect(asked()).toBe(1);
    expect(running()).toHaveTextContent(/^Đang chạy cho 1 agent: HLV sức khoẻ$/);
  });

  it("no longer names an agent whose browser was stopped since the page read the machine", async () => {
    show({ enabled: true, running: ["coach", "purchases"] }, named, ["purchases"]);
    expect(running()).toHaveTextContent("Đang chạy cho 2 agent: HLV sức khoẻ, Thủ kho");

    await settle();

    expect(running()).toHaveTextContent(/^Đang chạy cho 1 agent: Thủ kho$/);
  });

  it("is read again every few seconds while the page is looked at", async () => {
    clock();
    show({ enabled: true }, named);
    await settle();
    expect(asked()).toBe(1);

    await pass(BROWSER_POLL_MS - 1);
    expect(asked()).toBe(1);
    // An agent's call brings its browser up, and nobody tells the page.
    backend.browser.start("purchases");
    await pass(1);
    expect(asked()).toBe(2);
    expect(running()).toHaveTextContent(/^Đang chạy cho 1 agent: Thủ kho$/);

    // And an idle one stops by itself.
    backend.browser.route("/agents/purchases/browser/stop", "POST");
    await pass(BROWSER_POLL_MS);
    expect(asked()).toBe(3);
    expect(running()).toHaveTextContent(NOBODY);
    // One clock, however many answers have been drawn.
    expect(mock.getTimerCount()).toBe(1);
  });

  it("is not read while the page is out of view, and is read at once when it is looked at again", async () => {
    clock();
    show({ enabled: true }, named);
    await settle();

    const visibility = mock.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    look();
    await settle();
    backend.browser.start("coach");
    await pass(BROWSER_POLL_MS * 4);
    expect(asked()).toBe(1);
    expect(mock.getTimerCount()).toBe(0);
    expect(running()).toHaveTextContent(NOBODY);

    visibility.mockReturnValue("visible");
    look();
    await settle();
    expect(asked()).toBe(2);
    expect(running()).toHaveTextContent(/^Đang chạy cho 1 agent: HLV sức khoẻ$/);
    await pass(BROWSER_POLL_MS);
    expect(asked()).toBe(3);
  });

  it.each([
    ["switched off", { enabled: false }],
    ["with no browser installed", { enabled: true, installed: false, missing: "browser" as const }],
  ])("is asked of nobody on a machine %s, which has no browser to be up", async (_what, machine) => {
    clock();
    show(machine, named);
    await settle();
    await pass(BROWSER_POLL_MS * 3);
    look();
    await settle();

    expect(asked()).toBe(0);
    expect(mock.getTimerCount()).toBe(0);
    expect(running()).toHaveTextContent(NOBODY);
  });

  it("keeps what it shows while the server does not answer, and shows the next answer that comes", async () => {
    clock();
    show({ enabled: true, running: ["coach"] }, named);
    await settle();

    const before = screen.getByTestId("browser-machine").textContent;
    down = true;
    backend.browser.start("purchases");
    await pass(BROWSER_POLL_MS * 2);
    expect(running()).toHaveTextContent(/^Đang chạy cho 1 agent: HLV sức khoẻ$/);
    // The card has no error of its own to add: it keeps the last line it was told.
    expect(screen.getByTestId("browser-machine").textContent).toBe(before);

    down = false;
    await pass(BROWSER_POLL_MS);
    expect(running()).toHaveTextContent("Đang chạy cho 2 agent: HLV sức khoẻ, Thủ kho");
  });

  it("keeps what it shows when an answer says nothing of a browser at all", async () => {
    clock();
    show({ enabled: true, running: ["coach"] }, named);
    await settle();

    backend.browser.old = true;
    await pass(BROWSER_POLL_MS);

    expect(asked()).toBe(2);
    expect(running()).toHaveTextContent(/^Đang chạy cho 1 agent: HLV sức khoẻ$/);
    expect(state()).toHaveTextContent("Đang bật");
  });

  it("is not replaced by an answer that crossed a later one on the wire", async () => {
    const held: (() => void)[] = [];
    mock.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      const answer = await backend.fetch(input, init);
      await new Promise<void>((land) => held.push(land));
      return answer;
    });
    clock();
    show({ enabled: true }, named);
    // The first answer says nobody; the second, asked after the coach's browser came up, says one.
    backend.browser.start("coach");
    await pass(BROWSER_POLL_MS);
    expect(held).toHaveLength(2);

    held[1]();
    await settle();
    expect(running()).toHaveTextContent(/^Đang chạy cho 1 agent: HLV sức khoẻ$/);
    held[0]();
    await settle();

    expect(running()).toHaveTextContent(/^Đang chạy cho 1 agent: HLV sức khoẻ$/);
  });

  it("takes only that one line of an answer: the rest of the page stays as the page read it", async () => {
    backend.connections = { ...backend.connections, telegram: [{ agent_id: "coach", token_env: "COACH_BOT", configured: true, ignored: true }] };
    show({ enabled: true }, named, ["coach"]);
    await settle();

    expect(running()).toHaveTextContent(/^Đang chạy cho 1 agent: HLV sức khoẻ$/);
    expect(screen.queryByTestId("telegram-list")).not.toBeInTheDocument();
    expect(screen.getByText(vi.connectionsPage.noTelegram)).toBeInTheDocument();
  });

  it("says what the page says once the page reads the machine again as one with no browser to start", async () => {
    clock();
    const { rerender } = show({ enabled: true }, named, ["coach"]);
    await settle();
    expect(running()).toHaveTextContent(/^Đang chạy cho 1 agent: HLV sức khoẻ$/);
    expect(mock.getTimerCount()).toBe(1);

    // The server came back with its browser switched off, and the page read it so.
    const off = { ...base, browser: { ...browserMachine(), enabled: false, running: [] } };
    rerender(<ConnectionsPanel connections={off} credentials={credentials} mcp={mcp} agentName={named} onChanged={() => undefined} />);

    expect(running()).toHaveTextContent(NOBODY);
    expect(state()).toHaveTextContent(t.off);
    // And the card stops asking.
    expect(mock.getTimerCount()).toBe(0);
    await pass(BROWSER_POLL_MS * 2);
    expect(asked()).toBe(1);
  });

  it("ends with the page: no clock left, and nothing asked after it", async () => {
    clock();
    const { unmount } = show({ enabled: true }, named);
    await settle();
    expect(mock.getTimerCount()).toBe(1);

    unmount();

    expect(mock.getTimerCount()).toBe(0);
    await pass(BROWSER_POLL_MS * 2);
    look();
    await settle();
    expect(asked()).toBe(1);
  });
});
