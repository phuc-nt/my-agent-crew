// The machine's browser on the connections page: one card that sets nothing and says whether
// the crew may start a browser, which one, what is missing, and whose is up.
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi as mock } from "vitest";
import type { BrowserConnection, ConnectionsInfo, CredentialsInfo } from "../api/types";
import type { CredentialsController } from "../hooks/use-credentials";
import type { McpController } from "../hooks/use-mcp-servers";
import { vi } from "../i18n/vi";
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

/** The page as the server's answer draws it, on a machine that says `machine` of its browser. */
function show(machine: Partial<BrowserConnection> | null, agentName?: (id: string) => string) {
  const connections = machine === null ? base : { ...base, browser: { ...browserMachine(), running: [], ...machine } };
  render(<ConnectionsPanel connections={connections} credentials={credentials} mcp={mcp} agentName={agentName} onChanged={() => undefined} />);
}

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
