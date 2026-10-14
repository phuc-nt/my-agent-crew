import { describe, expect, it, vi as vitest } from "vitest";
import type { AgentBrowser, AgentInfo, ConnectionsInfo, RegistryTool } from "../api/types";
import { FakeBackend, fakeAgent } from "./fake-backend";
import { BROWSER_ACT_TOOLS, BROWSER_READ_TOOLS, type BrowserCrewMember, browserMachine, browserTab, FakeBrowser, TAB_UNKNOWN } from "./fake-browser";

const BASE = "/agents/coach/browser";
const CREW: BrowserCrewMember[] = [{ id: "default" }, { id: "coach", browser: "act" }, { id: "reader", browser: "read" }];

/** A browser on a machine that has one switched on, in a crew of three unless told another. */
function crewed(crew: BrowserCrewMember[] = CREW): FakeBrowser {
  return Object.assign(new FakeBrowser(), { crew: () => crew, machine: browserMachine({ enabled: true }) });
}

const read = (browser: FakeBrowser, agentId = "coach") => browser.route(`/agents/${agentId}/browser`, "GET")?.body as AgentBrowser;

describe("the browser routes both fakes answer", () => {
  it("reads an agent whose browser is not up: no tab, no idle time, and what its file and the machine say", () => {
    expect(crewed().route(BASE, "GET")).toEqual({
      status: 200,
      body: {
        mode: "act", enabled: true, installed: true, running: false, busy: false, idle_seconds: null, tabs: [],
        // No window is open on its profile, one can be, and nothing was ever written of what it holds.
        login: { open: false, until: null, available: true, why: "" },
        logins: null,
        logins_more: 0,
      },
    });
  });

  it("reads the machine's switch and whether a browser is installed as they are", () => {
    const browser = crewed();
    browser.machine = browserMachine({ enabled: false, installed: false, missing: "browser" });

    expect(read(browser)).toMatchObject({ mode: "act", enabled: false, installed: false, running: false });
    // An agent whose file says nothing of a browser reads as off.
    expect(read(browser, "default")).toMatchObject({ mode: "off" });
  });

  it("lists a running browser's tabs last used first, and of two used together the one opened later", () => {
    const browser = crewed().start(
      "coach",
      [
        browserTab({ id: 1, label: "main", idle_seconds: 240 }),
        browserTab({ id: 2, label: "cart", idle_seconds: 3 }),
        browserTab({ id: 3, label: "pay", idle_seconds: 3 }),
        browserTab({ id: 4, label: "job", idle_seconds: 61, conversation_id: null }),
      ],
      { busy: true, idleSeconds: 3 },
    );

    const told = read(browser);

    expect(told).toMatchObject({ running: true, busy: true, idle_seconds: 3 });
    expect(told.tabs.map((tab) => tab.label)).toEqual(["pay", "cart", "job", "main"]);
    // The order the tabs were opened in is the browser's own, and reading does not change it.
    expect(browser.tabIds("coach")).toEqual([1, 2, 3, 4]);
  });

  it("reads a browser that is up with no state said as idle from now", () => {
    expect(read(crewed().start("coach"))).toMatchObject({ running: true, busy: false, idle_seconds: 0, tabs: [] });
  });

  it("stops a browser that is up, and says there was none the second time", () => {
    const browser = crewed().start("coach", [browserTab()]);

    expect(browser.route(`${BASE}/stop`, "POST")).toEqual({ status: 200, body: { stopped: true } });
    expect(browser.running("coach")).toBe(false);
    expect(read(browser)).toMatchObject({ running: false, idle_seconds: null, tabs: [] });
    expect(browser.route(`${BASE}/stop`, "POST")).toEqual({ status: 200, body: { stopped: false } });
  });

  it("closes a tab by its id, and answers a tab that is gone in the server's own sentence", () => {
    const browser = crewed().start("coach", [browserTab({ id: 1 }), browserTab({ id: 2, label: "cart" })]);

    expect(browser.route(`${BASE}/tabs/2`, "DELETE")).toEqual({ status: 200, body: { closed: 2 } });
    expect(browser.tabIds("coach")).toEqual([1]);
    expect(browser.route(`${BASE}/tabs/2`, "DELETE")).toEqual({ status: 404, body: { detail: TAB_UNKNOWN } });
    expect(TAB_UNKNOWN).toBe("Không còn tab này trong trình duyệt của agent.");
    // The browser stays up with the tab it has left.
    expect(browser.running("coach")).toBe(true);
  });

  it("has no tab to close in a browser that is not up", () => {
    expect(crewed().route(`${BASE}/tabs/1`, "DELETE")).toEqual({ status: 404, body: { detail: TAB_UNKNOWN } });
  });

  it("refuses a tab id that is no number before it looks at the agent", () => {
    const browser = crewed().start("coach", [browserTab()]);

    expect(browser.route(`${BASE}/tabs/main`, "DELETE")?.status).toBe(422);
    expect(browser.route("/agents/nobody/browser/tabs/main", "DELETE")?.status).toBe(422);
    expect(browser.tabIds("coach")).toEqual([1]);
  });

  it("answers 404 for an agent the crew does not have, on each of the five", () => {
    const browser = crewed();
    const unknown = { status: 404, body: { detail: "unknown agent nobody" } };

    expect(browser.route("/agents/nobody/browser", "GET")).toEqual(unknown);
    expect(browser.route("/agents/nobody/browser/stop", "POST")).toEqual(unknown);
    expect(browser.route("/agents/nobody/browser/tabs/1", "DELETE")).toEqual(unknown);
    expect(browser.route("/agents/nobody/browser/login", "POST", {})).toEqual(unknown);
    expect(browser.route("/agents/nobody/browser/login/done", "POST")).toEqual(unknown);
  });

  it("answers each path to its own method only", () => {
    const browser = crewed().start("coach", [browserTab()]);

    expect(browser.route(BASE, "POST")?.status).toBe(405);
    expect(browser.route(`${BASE}/stop`, "GET")?.status).toBe(405);
    expect(browser.route(`${BASE}/tabs/1`, "GET")?.status).toBe(405);
    expect(browser.route(`${BASE}/login`, "GET")?.status).toBe(405);
    expect(browser.route(`${BASE}/login/done`, "GET")?.status).toBe(405);
    // Nothing was stopped, closed or opened by a request the server would not have routed.
    expect(browser.running("coach")).toBe(true);
    expect(browser.tabIds("coach")).toEqual([1]);
    expect(read(browser).login).toMatchObject({ open: false });
  });

  it("leaves every other path to the fake it sits in", () => {
    const browser = crewed();

    for (const path of [
      "/agents/coach", "/agents/coach/browsers", "/agents/coach/browser/tabs", "/agents/coach/browser/stop/now",
      "/agents/coach/browser/login/now", "/agents/coach/browser/done", "/agents/coach/browser/login/done/now", "/connections", "/browser",
    ])
      expect(browser.route(path, "GET")).toBeNull();
  });

  it("answers as a server from before the browser when told to: no route, no key, no tool", () => {
    const browser = crewed().start("coach", [browserTab()]);
    browser.old = true;

    expect(browser.route(BASE, "GET")).toEqual({ status: 404, body: { detail: "Not Found" } });
    expect(browser.route(`${BASE}/stop`, "POST")?.status).toBe(404);
    expect(browser.route(`${BASE}/tabs/1`, "DELETE")?.status).toBe(404);
    expect(browser.route(`${BASE}/login`, "POST", {})?.status).toBe(404);
    expect(browser.route(`${BASE}/login/done`, "POST")?.status).toBe(404);
    expect(browser.status()).toBeUndefined();
    expect(browser.registryTools()).toEqual([]);
  });

  it("refuses a kind of request for as long as a test says so, and nothing else", () => {
    const browser = crewed().start("coach", [browserTab()]);
    browser.refuse.close = { status: 500, detail: "trình duyệt không trả lời" };

    expect(browser.route(`${BASE}/tabs/1`, "DELETE")).toEqual({ status: 500, body: { detail: "trình duyệt không trả lời" } });
    expect(browser.tabIds("coach")).toEqual([1]);
    expect(browser.route(BASE, "GET")?.status).toBe(200);
    browser.refuse = {};
    expect(browser.route(`${BASE}/tabs/1`, "DELETE")).toEqual({ status: 200, body: { closed: 1 } });
  });
});

describe("the machine's browser, as GET /connections reports it", () => {
  it("is the machine's own facts with the agents whose browser is up, by id", () => {
    const browser = crewed().start("reader").start("coach");

    expect(browser.status()).toEqual({
      enabled: true, channel: "chromium", installed: true, version: "141.0.7390.37", missing: "", install_command: "",
      running: ["coach", "reader"],
    });
  });

  it("names nobody while no browser is up, and forgets one that was stopped", () => {
    const browser = crewed();
    expect(browser.status()?.running).toEqual([]);

    browser.start("coach");
    browser.route(`${BASE}/stop`, "POST");

    expect(browser.status()?.running).toEqual([]);
  });

  it("is switched off and installed on a machine whose file says nothing of it", () => {
    expect(new FakeBrowser().status()).toMatchObject({ enabled: false, channel: "chromium", installed: true, missing: "", running: [] });
  });
});

describe("what a save of an agent does to its browser", () => {
  it.each(["off", undefined] as const)("stops it when the file is left at %s", (mode) => {
    const browser = crewed().start("coach", [browserTab()]);

    browser.saved("coach", mode);

    expect(browser.running("coach")).toBe(false);
  });

  it.each(["read", "act"] as const)("leaves it up when the file is left at %s", (mode) => {
    const browser = crewed().start("coach", [browserTab()]);

    browser.saved("coach", mode);

    expect(browser.running("coach")).toBe(true);
    expect(browser.tabIds("coach")).toEqual([1]);
  });
});

describe("the browser's rows of GET /tools", () => {
  const names = (rows: RegistryTool[]) => rows.map((row) => row.name);

  it("are the eight tools by name, each marked as handed outside any list and never optional", () => {
    const rows = crewed().registryTools();

    expect(names(rows)).toEqual([
      "browser_act", "browser_download", "browser_navigate", "browser_pdf", "browser_screenshot", "browser_snapshot", "browser_tabs", "browser_text",
    ]);
    expect(names(rows).sort()).toEqual([...BROWSER_READ_TOOLS, ...BROWSER_ACT_TOOLS].sort());
    for (const row of rows) expect(row).toMatchObject({ optional: false, with_browser: true });
  });

  it("ask first for the three that open an address or touch a page, and for no other", () => {
    const asks = crewed().registryTools().filter((row) => row.requires_approval);

    expect(names(asks)).toEqual(["browser_act", "browser_download", "browser_navigate"]);
  });

  it("name the agents whose file asks for each: reading brings six, acting two more", () => {
    const held = Object.fromEntries(crewed().registryTools().map((row) => [row.name, row.agents]));

    expect(BROWSER_READ_TOOLS).toHaveLength(6);
    expect(BROWSER_ACT_TOOLS).toEqual(["browser_act", "browser_download"]);
    for (const name of BROWSER_ACT_TOOLS) expect(held[name]).toEqual(["coach"]);
    for (const name of BROWSER_READ_TOOLS) expect(held[name]).toEqual(["coach", "reader"]);
  });

  it("have no row for a tool nobody holds, and none at all in a crew that asks for no browser", () => {
    const readers = crewed([{ id: "default" }, { id: "reader", browser: "read" }]);
    for (const name of BROWSER_ACT_TOOLS) expect(names(readers.registryTools())).not.toContain(name);
    expect(names(readers.registryTools())).toContain("browser_pdf");
    expect(readers.registryTools()).toHaveLength(6);

    expect(crewed([{ id: "default" }, { id: "coach", browser: "off" }]).registryTools()).toEqual([]);
  });

  it("are none on a machine that has the browser switched off or not installed", () => {
    const off = crewed();
    off.machine = browserMachine({ enabled: false });
    expect(off.registryTools()).toEqual([]);

    const missing = crewed();
    missing.machine = browserMachine({ enabled: true, installed: false, missing: "browser" });
    expect(missing.registryTools()).toEqual([]);
  });
});

describe("the browser as the fake server wires it", () => {
  const coach: AgentInfo = { ...fakeAgent, id: "coach", name: "HLV", is_master: false, browser: "act", browser_hosts: ["shop.example"] };

  function served() {
    const backend = new FakeBackend();
    backend.agents = [fakeAgent, coach];
    backend.browser.machine = browserMachine({ enabled: true });
    vitest.stubGlobal("fetch", backend.fetch);
    return backend;
  }

  const ask = async (path: string, method = "GET", body?: unknown) => {
    const response = await fetch(`/api${path}`, { method, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: response.status, body: await response.json() };
  };

  it("reads the crew it serves, so an agent added to it has a browser to read", async () => {
    served();

    expect(await ask("/agents/coach/browser")).toMatchObject({ status: 200, body: { mode: "act", running: false } });
    expect((await ask("/agents/nobody/browser")).status).toBe(404);
  });

  it("keeps a saved level and host list, and reads both back", async () => {
    const backend = served();

    const saved = await ask("/agents/coach", "PATCH", { profile: { browser: "read", browser_hosts: [" docs.example ", "*.shop.example"] } });

    expect(saved.body.profile).toMatchObject({ browser: "read", browser_hosts: ["docs.example", "*.shop.example"] });
    expect(backend.agents[1]).toMatchObject({ browser: "read", browser_hosts: ["docs.example", "*.shop.example"] });
    expect((await ask("/agents")).body[1]).toMatchObject({ browser: "read", browser_hosts: ["docs.example", "*.shop.example"] });
    expect((await ask("/agents/coach/browser")).body.mode).toBe("read");
  });

  it("refuses a level or a host the server would refuse, with a 422 and the agent as it was", async () => {
    const backend = served();

    expect((await ask("/agents/coach", "PATCH", { profile: { browser: "on" } })).status).toBe(422);
    expect((await ask("/agents/coach", "PATCH", { profile: { browser_hosts: ["https://shop.example"] } })).status).toBe(422);
    expect(backend.agents[1]).toMatchObject({ browser: "act", browser_hosts: ["shop.example"] });
  });

  it("stops the agent's browser on a save that leaves the level at off, and on no other save", async () => {
    const backend = served();
    backend.browser.start("coach", [browserTab()]);

    await ask("/agents/coach", "PATCH", { profile: { name: "HLV mới" } });
    expect(backend.browser.running("coach")).toBe(true);
    await ask("/agents/coach", "PATCH", { profile: { browser: "read" } });
    expect(backend.browser.running("coach")).toBe(true);

    await ask("/agents/coach", "PATCH", { profile: { browser: "off" } });

    expect(backend.browser.running("coach")).toBe(false);
    expect((await ask("/agents/coach/browser")).body).toMatchObject({ mode: "off", running: false, tabs: [] });
  });

  it("puts the machine's browser in the connections it answers, and in the answer to a save of routes", async () => {
    const backend = served();
    backend.browser.start("coach");

    const connections = (await ask("/connections")).body as ConnectionsInfo;
    expect(connections.browser).toMatchObject({ enabled: true, running: ["coach"] });

    const routed = (await ask("/connections/routes", "PUT", { routes: [{ provider: "fake", model: "echo" }] })).body as ConnectionsInfo;
    expect(routed.browser).toMatchObject({ enabled: true, running: ["coach"] });
  });

  it("answers neither with the key as a server from before the browser", async () => {
    const backend = served();
    backend.browser.old = true;

    expect((await ask("/connections")).body).not.toHaveProperty("browser");
    expect((await ask("/connections/routes", "PUT", { routes: [] })).body).not.toHaveProperty("browser");
    expect((await ask("/agents/coach/browser")).status).toBe(404);
  });

  it("lists the browser's tools with the crew's own, for the agents that hold them", async () => {
    served();

    const tools = (await ask("/tools")).body as RegistryTool[];

    expect(tools.find((tool) => tool.name === "browser_act")).toMatchObject({ agents: ["coach"], with_browser: true, requires_approval: true });
    expect(tools.find((tool) => tool.name === "write_file")).not.toHaveProperty("with_browser");
    expect(tools.find((tool) => tool.name === "browser_download")).toMatchObject({ agents: ["coach"], with_browser: true, requires_approval: true });
    expect(tools.find((tool) => tool.name === "browser_pdf")).toMatchObject({ agents: ["coach"], with_browser: true, requires_approval: false });
    expect(tools.filter((tool) => tool.with_browser)).toHaveLength(8);
  });
});
