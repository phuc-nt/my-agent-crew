import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentBrowser, AgentInfo, RegistryTool } from "../api/types";
import { FakeBackend, fakeAgent } from "./fake-backend";
import { type BrowserCrewMember, browserMachine, browserTab, FakeBrowser } from "./fake-browser";
import { LOGIN_BUSY, LOGIN_LOCKED, LOGIN_NO_CONSOLE, LOGIN_OFF, moment, OPEN_SECONDS, TOLD, URL_SCHEME } from "./fake-browser-login";

const BASE = "/agents/coach/browser";
const NINE = new Date("2026-10-14T02:00:00Z");
const later = (seconds: number) => new Date(NINE.getTime() + seconds * 1000);
/** A day well after the clock of any test here, and one before it. */
const NOVEMBER = new Date("2026-11-11T17:30:00Z");
const DECEMBER = new Date("2026-12-01T00:00:00Z");
const GONE = new Date("2026-10-13T00:00:00Z");

/** A browser on a machine that has one switched on, with a screen to show a window on, in a
 *  crew whose coach has no hosts of its own unless `coach` gives it some. */
function crewed(coach: Partial<BrowserCrewMember> = {}): FakeBrowser {
  const crew: BrowserCrewMember[] = [{ id: "default" }, { id: "coach", browser: "act", ...coach }, { id: "reader", browser: "read" }];
  const browser = Object.assign(new FakeBrowser(), { crew: () => crew, machine: browserMachine({ enabled: true }) });
  browser.login.now = () => NINE;
  return browser;
}

const read = (browser: FakeBrowser, agentId = "coach") => browser.route(`/agents/${agentId}/browser`, "GET")?.body as AgentBrowser;
const open = (browser: FakeBrowser, body: unknown = {}, agentId = "coach") => browser.route(`/agents/${agentId}/browser/login`, "POST", body);
const done = (browser: FakeBrowser, agentId = "coach") => browser.route(`/agents/${agentId}/browser/login/done`, "POST");
const AT_QUARTER_PAST = { status: 200, body: { open: true, until: "2026-10-14T02:15:00+00:00" } };
const refused = (status: number, detail: string) => ({ status, body: { detail } });

afterEach(() => {
  vitest.unstubAllGlobals();
});

describe("the window a person signs in through, as both fakes answer it", () => {
  it("opens for a quarter of an hour, and the agent's browser is read as held by it", () => {
    const browser = crewed();

    expect(open(browser)).toEqual(AT_QUARTER_PAST);
    expect(OPEN_SECONDS).toBe(900);
    expect(read(browser).login).toEqual({ open: true, until: "2026-10-14T02:15:00+00:00", available: false, why: "" });
  });

  it("writes a moment as the server does: UTC, to the second, with its offset spelled out", () => {
    expect(moment(new Date("2026-11-12T00:30:15.250+07:00"))).toBe("2026-11-11T17:30:15+00:00");
  });

  it("answers the window that is open when asked again, and keeps it open no longer", () => {
    const browser = crewed();
    open(browser);
    browser.login.now = () => later(600);

    expect(open(browser, { url: "https://shop.example/login" })).toEqual(AT_QUARTER_PAST);
    expect(read(browser).login?.until).toBe("2026-10-14T02:15:00+00:00");
  });

  it("answers an open window still behind a screen locked since", () => {
    const browser = crewed();
    open(browser);
    browser.login.screen = "locked";

    expect(open(browser)).toEqual(AT_QUARTER_PAST);
    expect(read(browser).login).toMatchObject({ open: true, why: "" });
  });

  it("stops the agent's own browser as it opens: the window holds the profile", () => {
    const browser = crewed().start("coach", [browserTab({ id: 1 }), browserTab({ id: 2 })]);
    browser.start("reader", [browserTab({ id: 3 })]);

    expect(open(browser)).toEqual(AT_QUARTER_PAST);

    expect(browser.running("coach")).toBe(false);
    expect(read(browser)).toMatchObject({ running: false, tabs: [], idle_seconds: null });
    expect(browser.running("reader")).toBe(true);
  });

  it.each([
    ["with no screen to show it on", "none", "no_console", LOGIN_NO_CONSOLE],
    ["behind a locked screen", "locked", "locked", LOGIN_LOCKED],
  ] as const)("opens none %s: the read says why in a word, and the request is refused in a sentence", (_, screen, why, said) => {
    const browser = crewed().start("coach", [browserTab()]);
    browser.login.screen = screen;

    expect(read(browser).login).toEqual({ open: false, until: null, available: false, why });
    expect(open(browser)).toEqual(refused(409, said));
    expect(read(browser).login?.open).toBe(false);
    // Nothing was stopped for a window that did not open.
    expect(browser.running("coach")).toBe(true);
  });

  it("opens none under a call that is using the browser, which stays up", () => {
    const browser = crewed().start("coach", [browserTab()], { busy: true });

    expect(read(browser).login).toEqual({ open: false, until: null, available: false, why: "busy" });
    expect(open(browser)).toEqual(refused(409, LOGIN_BUSY));
    expect(browser.running("coach")).toBe(true);
    expect(browser.tabIds("coach")).toEqual([1]);
  });

  it("says the screen before the call where both are in the way", () => {
    const browser = crewed().start("coach", [browserTab()], { busy: true });
    browser.login.screen = "locked";
    expect(read(browser).login?.why).toBe("locked");
    expect(open(browser)).toEqual(refused(409, LOGIN_LOCKED));

    browser.login.screen = "none";
    expect(read(browser).login?.why).toBe("no_console");
  });

  it("opens one beside a browser that is up and idle", () => {
    const browser = crewed().start("coach", [browserTab()]);

    expect(read(browser).login).toEqual({ open: false, until: null, available: true, why: "" });
    expect(open(browser)).toEqual(AT_QUARTER_PAST);
  });

  it.each([
    ["whose file asks for none", { browser: "off" as const }, {}],
    ["whose file says nothing of one", { browser: undefined }, {}],
    ["on a machine with the browser switched off", {}, { enabled: false }],
    ["on a machine with none installed", {}, { installed: false, missing: "browser" as const }],
  ])("has no window for an agent %s, and nothing to tell of where it is signed in", (_, coach, machine) => {
    const browser = crewed(coach);
    browser.machine = browserMachine({ enabled: true, ...machine });
    browser.login.signedIn("coach", { "shop.example": NOVEMBER });

    expect(read(browser).login).toEqual({ open: false, until: null, available: false, why: "off" });
    expect(read(browser).logins).toBeNull();
    expect(open(browser, { url: "https://shop.example/" })).toEqual(refused(409, LOGIN_OFF));
    expect(read(browser).login?.open).toBe(false);
    expect(done(browser)).toEqual({ status: 200, body: { closed: false } });
  });

  it("says an agent has no browser before it looks at the address", () => {
    expect(open(crewed({ browser: "off" }), { url: "ftp://shop.example" })).toEqual(refused(409, LOGIN_OFF));
  });
});

describe("the address a sign-in window opens on", () => {
  it.each([
    "ftp://shop.example/tep",
    "shop.example",
    "javascript:alert(1)",
    "file:///etc/hosts",
    "https://user@shop.example/",
    "https://shop.example\\@evil.example/",
    "https://shop%2eexample/",
    "https://shop.example/a b",
    "https://",
  ])("is refused as %s, in the sentence the browser's own tool uses, and no window opens", (url) => {
    const browser = crewed().start("coach", [browserTab()]);

    expect(open(browser, { url })).toEqual(refused(422, URL_SCHEME));
    expect(read(browser).login?.open).toBe(false);
    expect(browser.running("coach")).toBe(true);
  });

  it.each([
    ["nothing", {}],
    ["no body at all", undefined],
    ["a null body", null],
    ["an empty address", { url: "" }],
    ["an address of blanks", { url: "   " }],
    ["a full address", { url: "https://shop.example/login?next=/don-hang" }],
    ["a host alone", { url: "http://shop.example" }],
    ["an address with blanks around it", { url: "  https://shop.example/login  " }],
  ])("is taken where the request gives %s", (_, body) => {
    expect(open(crewed(), body)).toEqual(AT_QUARTER_PAST);
  });

  it("is refused before the window that is open or the screen is looked at", () => {
    const opened = crewed();
    open(opened);
    expect(open(opened, { url: "ftp://shop.example" })).toEqual(refused(422, URL_SCHEME));
    expect(read(opened).login?.open).toBe(true);

    const locked = crewed();
    locked.login.screen = "locked";
    expect(open(locked, { url: "ftp://shop.example" })).toEqual(refused(422, URL_SCHEME));

    const busy = crewed().start("coach", [browserTab()], { busy: true });
    expect(open(busy, { url: "shop.example" })).toEqual(refused(422, URL_SCHEME));
  });

  it("is refused as the server's validation refuses one that is no text", () => {
    const browser = crewed();

    const answer = open(browser, { url: 5 });

    expect(answer?.status).toBe(422);
    expect(Array.isArray((answer?.body as { detail: unknown }).detail)).toBe(true);
    expect(read(browser).login?.open).toBe(false);
  });
});

describe("a sign-in window closing", () => {
  it("closes when a person says they are done, and says there was none the second time", () => {
    const browser = crewed();
    open(browser);

    expect(done(browser)).toEqual({ status: 200, body: { closed: true } });
    expect(read(browser).login).toEqual({ open: false, until: null, available: true, why: "" });
    expect(done(browser)).toEqual({ status: 200, body: { closed: false } });
  });

  it("is open a second short of its time, and closed by itself once that has come", () => {
    const browser = crewed();
    open(browser);

    browser.login.now = () => later(OPEN_SECONDS - 1);
    expect(read(browser).login).toMatchObject({ open: true, available: false });

    browser.login.now = () => later(OPEN_SECONDS);
    expect(read(browser).login).toEqual({ open: false, until: null, available: true, why: "" });
    expect(done(browser)).toEqual({ status: 200, body: { closed: false } });
  });

  it("opens anew for a quarter of an hour from then, once the last closed by itself", () => {
    const browser = crewed();
    open(browser);
    browser.login.now = () => later(OPEN_SECONDS + 60);

    expect(open(browser)).toEqual({ status: 200, body: { open: true, until: "2026-10-14T02:31:00+00:00" } });
  });

  it("closes with the agent's browser when that is stopped: the stop says there was something to stop", () => {
    const browser = crewed();
    open(browser);

    expect(browser.route(`${BASE}/stop`, "POST")).toEqual({ status: 200, body: { stopped: true } });
    expect(read(browser).login?.open).toBe(false);
    expect(browser.route(`${BASE}/stop`, "POST")).toEqual({ status: 200, body: { stopped: false } });
  });

  it("closes on a save that leaves the agent's level at off, and on no other save", () => {
    const browser = crewed();
    open(browser);

    browser.saved("coach", "read");
    expect(browser.login.window("coach")).toEqual(later(OPEN_SECONDS));
    browser.saved("coach", "act");
    expect(browser.login.window("coach")).toBeDefined();

    browser.saved("coach", "off");
    expect(browser.login.window("coach")).toBeUndefined();
  });

  it("is one agent's own: another's window is left as it is", () => {
    const browser = crewed();
    open(browser);
    open(browser, {}, "reader");

    expect(done(browser)).toEqual({ status: 200, body: { closed: true } });

    expect(read(browser, "reader").login?.open).toBe(true);
    expect(read(browser).login?.open).toBe(false);
    browser.route("/agents/reader/browser/stop", "POST");
    expect(read(browser, "reader").login?.open).toBe(false);
  });
});

describe("where an agent's browser may still be signed in, as both fakes tell it", () => {
  it("has nothing to tell of a profile no browser ever closed on", () => {
    expect(read(crewed()).logins).toBeNull();
    expect(read(crewed({ browser_hosts: ["shop.example"] })).logins).toBeNull();
  });

  it("tells of no host once a browser is up on the profile, and still once it went down", () => {
    const browser = crewed().start("coach", [browserTab()]);
    expect(read(browser).logins).toEqual([]);

    browser.route(`${BASE}/stop`, "POST");
    expect(read(browser).logins).toEqual([]);
  });

  it("tells of no host while a window is open on the profile, and still once it closed", () => {
    const browser = crewed();
    open(browser);
    expect(read(browser).logins).toEqual([]);

    done(browser);
    expect(read(browser).logins).toEqual([]);
  });

  it("writes what the profile held when a window closed by itself, too", () => {
    const browser = crewed();
    open(browser);
    browser.login.now = () => later(OPEN_SECONDS + 1);

    expect(read(browser).login?.open).toBe(false);
    expect(read(browser).logins).toEqual([]);
  });

  it("tells an agent with hosts of its own of each of them in the order of its file, the ones holding nothing too", () => {
    const browser = crewed({ browser_hosts: ["track.example", "shop.example", "*.bank.example", "docs.example"] });
    browser.login.signedIn("coach", { "shop.example": NOVEMBER, "www.bank.example": DECEMBER, "other.example": DECEMBER });

    expect(read(browser).logins).toEqual([
      { host: "track.example", until: null },
      { host: "shop.example", until: "2026-11-11T17:30:00+00:00" },
      { host: "*.bank.example", until: "2026-12-01T00:00:00+00:00" },
      { host: "docs.example", until: null },
    ]);
  });

  it.each([
    ["the host itself", "shop.example", "shop.example", true],
    ["a host under it", "shop.example", "pay.shop.example", true],
    ["the domain it sits under", "pay.shop.example", "shop.example", true],
    ["the bare domain of a starred one", "*.shop.example", "shop.example", true],
    ["a host under a starred one", "*.shop.example", "a.b.shop.example", true],
    ["a name that only ends alike", "shop.example", "notshop.example", false],
    ["a name it only ends like", "notshop.example", "shop.example", false],
    ["a host beside it", "pay.shop.example", "www.shop.example", false],
  ])("counts for one of its hosts a cookie of %s: %s against %s", (_, pattern, host, counted) => {
    const browser = crewed({ browser_hosts: [pattern] });
    browser.login.signedIn("coach", { [host]: NOVEMBER });

    expect(read(browser).logins).toEqual([{ host: pattern, until: counted ? "2026-11-11T17:30:00+00:00" : null }]);
  });

  it("says for a host the last moment any cookie that counts for it runs out", () => {
    const browser = crewed({ browser_hosts: ["shop.example"] });
    browser.login.signedIn("coach", { "pay.shop.example": DECEMBER, "shop.example": NOVEMBER, "www.shop.example": later(60) });

    expect(read(browser).logins).toEqual([{ host: "shop.example", until: "2026-12-01T00:00:00+00:00" }]);
  });

  it("leaves out a cookie that has run out, and one running out this very second", () => {
    const browser = crewed({ browser_hosts: ["shop.example", "docs.example"] });
    browser.login.signedIn("coach", { "shop.example": GONE, "docs.example": NINE });
    expect(read(browser).logins).toEqual([
      { host: "shop.example", until: null },
      { host: "docs.example", until: null },
    ]);

    const plain = crewed();
    plain.login.signedIn("coach", { "shop.example": GONE, "docs.example": NINE, "bank.example": later(1) });
    expect(read(plain).logins).toEqual([{ host: "bank.example", until: "2026-10-14T02:00:01+00:00" }]);
  });

  it("says a host written twice in the file once, where it first stands", () => {
    const browser = crewed({ browser_hosts: ["shop.example", "docs.example", "shop.example"] });
    browser.login.signedIn("coach", { "shop.example": NOVEMBER });

    expect(read(browser).logins?.map((one) => one.host)).toEqual(["shop.example", "docs.example"]);
  });

  it("tells an agent with no hosts of its own of the hosts that hold something, by name", () => {
    const browser = crewed();
    browser.login.signedIn("coach", { "shop.example": NOVEMBER, "bank.example": DECEMBER, "mail.example": NOVEMBER });

    expect(read(browser).logins).toEqual([
      { host: "bank.example", until: "2026-12-01T00:00:00+00:00" },
      { host: "mail.example", until: "2026-11-11T17:30:00+00:00" },
      { host: "shop.example", until: "2026-11-11T17:30:00+00:00" },
    ]);
  });

  it("tells such an agent of fifty at most, the first by name", () => {
    const browser = crewed();
    const names = Array.from({ length: 53 }, (_, at) => `h${String(52 - at).padStart(2, "0")}.example`);
    browser.login.signedIn("coach", Object.fromEntries(names.map((name) => [name, NOVEMBER])));

    const told = read(browser).logins ?? [];

    expect(TOLD).toBe(50);
    expect(told).toHaveLength(50);
    expect(told[0].host).toBe("h00.example");
    expect(told[49].host).toBe("h49.example");
  });

  it("says beside the list how many more hold a sign-in than the fifty it tells of", () => {
    const browser = crewed();
    const sign = (count: number, extra: Record<string, Date> = {}) =>
      browser.login.signedIn("coach", { ...Object.fromEntries(Array.from({ length: count }, (_, at) => [`h${at}.example`, NOVEMBER])), ...extra });

    sign(53);
    expect(read(browser).logins_more).toBe(3);
    // A host whose sign-in ran out holds nothing: it was not left out.
    sign(53, { "old.example": new Date("2026-10-13T00:00:00Z") });
    expect(read(browser).logins_more).toBe(3);
    // A list that was not cut leaves none out, and where there is no list there is no more of it.
    sign(50);
    expect(read(browser).logins_more).toBe(0);
    expect(read(browser, "reader")).toMatchObject({ logins: null, logins_more: 0 });
  });

  it("leaves none out of the list of an agent that has hosts of its own", () => {
    const browser = crewed({ browser_hosts: ["shop.example"] });
    browser.login.signedIn("coach", Object.fromEntries(Array.from({ length: 53 }, (_, at) => [`h${at}.example`, NOVEMBER])));

    expect(read(browser)).toMatchObject({ logins: [{ host: "shop.example", until: null }], logins_more: 0 });
  });

  it("tells an agent with a list of every host of it, were it longer than fifty", () => {
    const hosts = Array.from({ length: 53 }, (_, at) => `h${at}.example`);
    const browser = crewed({ browser_hosts: hosts });
    browser.login.signedIn("coach", {});

    expect(read(browser).logins?.map((one) => one.host)).toEqual(hosts);
  });

  it("keeps what one agent's profile holds from another's", () => {
    const browser = crewed();
    browser.login.signedIn("coach", { "shop.example": NOVEMBER });

    expect(read(browser, "reader").logins).toBeNull();
    browser.start("reader");
    expect(read(browser, "reader").logins).toEqual([]);
  });
});

describe("a server that has the browser and not yet the sign-in window", () => {
  const before = () => {
    const browser = crewed().start("coach", [browserTab()]);
    browser.login.old = true;
    browser.login.signedIn("coach", { "shop.example": NOVEMBER });
    return browser;
  };

  it("reads an agent's browser with neither key", () => {
    const told = read(before());

    expect(told).not.toHaveProperty("login");
    expect(told).not.toHaveProperty("logins");
    expect(told).not.toHaveProperty("logins_more");
    expect(told).toMatchObject({ mode: "act", running: true });
  });

  it("has neither route, whatever the method, and still stops a browser and closes a tab", () => {
    const browser = before();

    for (const path of [`${BASE}/login`, `${BASE}/login/done`]) {
      for (const method of ["POST", "GET"]) expect(browser.route(path, method, {})).toEqual({ status: 404, body: { detail: "Not Found" } });
    }
    expect(browser.route(`${BASE}/tabs/1`, "DELETE")).toEqual({ status: 200, body: { closed: 1 } });
    expect(browser.route(`${BASE}/stop`, "POST")).toEqual({ status: 200, body: { stopped: true } });
  });

  it("lists the six tools it had: neither the page saved as a file nor the download", () => {
    const names = before().registryTools().map((tool) => tool.name);

    expect(names).toEqual(["browser_act", "browser_navigate", "browser_screenshot", "browser_snapshot", "browser_tabs", "browser_text"]);
  });
});

describe("the sign-in window as the fake server wires it", () => {
  const coach: AgentInfo = { ...fakeAgent, id: "coach", name: "HLV", is_master: false, browser: "act", browser_hosts: ["shop.example"] };

  function served() {
    const backend = new FakeBackend();
    backend.agents = [fakeAgent, coach];
    backend.browser.machine = browserMachine({ enabled: true });
    backend.browser.login.now = () => NINE;
    vitest.stubGlobal("fetch", backend.fetch);
    return backend;
  }

  const ask = async (path: string, method = "GET", body?: unknown) => {
    const response = await fetch(`/api${path}`, { method, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: response.status, body: await response.json() };
  };

  it("hands the address a request carries to the window, so a bad one is refused and a good one opens", async () => {
    served();

    expect(await ask(`${BASE}/login`, "POST", { url: "ftp://shop.example" })).toEqual(refused(422, URL_SCHEME));
    expect(await ask(`${BASE}/login`, "POST", { url: "https://shop.example/login" })).toEqual(AT_QUARTER_PAST);
    expect((await ask(BASE)).body.login).toMatchObject({ open: true, until: "2026-10-14T02:15:00+00:00" });
    expect(await ask(`${BASE}/login/done`, "POST")).toEqual({ status: 200, body: { closed: true } });
  });

  it("opens one on a request that carries nothing", async () => {
    served();

    expect(await ask(`${BASE}/login`, "POST")).toEqual(AT_QUARTER_PAST);
  });

  it("tells of the hosts of the agent's own file, as the crew it serves has them", async () => {
    const backend = served();
    backend.browser.login.signedIn("coach", { "pay.shop.example": NOVEMBER, "other.example": NOVEMBER });

    expect((await ask(BASE)).body.logins).toEqual([{ host: "shop.example", until: "2026-11-11T17:30:00+00:00" }]);
  });

  it("refuses either request with what a test sets, for as long as it is set", async () => {
    const backend = served();
    backend.browser.refuse.login = { status: 409, detail: "Không mở được cửa sổ." };
    expect(await ask(`${BASE}/login`, "POST", {})).toEqual(refused(409, "Không mở được cửa sổ."));
    expect((await ask(BASE)).body.login.open).toBe(false);

    backend.browser.refuse.login = undefined;
    await ask(`${BASE}/login`, "POST", {});
    backend.browser.refuse.done = { status: 500, detail: "boom" };
    expect(await ask(`${BASE}/login/done`, "POST")).toEqual(refused(500, "boom"));
    expect((await ask(BASE)).body.login.open).toBe(true);
  });

  it("closes the window on a save that leaves the agent's level at off", async () => {
    const backend = served();
    await ask(`${BASE}/login`, "POST", {});

    await ask("/agents/coach", "PATCH", { profile: { name: "HLV mới" } });
    expect(backend.browser.login.window("coach")).toBeDefined();

    await ask("/agents/coach", "PATCH", { profile: { browser: "off" } });
    expect(backend.browser.login.window("coach")).toBeUndefined();
    expect((await ask(BASE)).body.login).toEqual({ open: false, until: null, available: false, why: "off" });
  });

  it("lists the tools that came with the window among the browser's, unless the server is from before it", async () => {
    const backend = served();
    const marked = async () => ((await ask("/tools")).body as RegistryTool[]).filter((tool) => tool.with_browser).map((tool) => tool.name);

    expect(await marked()).toEqual(expect.arrayContaining(["browser_pdf", "browser_download"]));

    backend.browser.login.old = true;
    expect(await marked()).toHaveLength(6);
    expect(await marked()).not.toContain("browser_pdf");
    expect(await marked()).not.toContain("browser_download");
  });
});
