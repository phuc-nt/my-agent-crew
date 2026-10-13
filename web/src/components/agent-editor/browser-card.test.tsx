// What an agent's browser is doing now, on the agent's page: the states the card draws, the
// two things a person can do to it at once, and how the state is read again.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentBrowser, BrowserMode } from "../../api/types";
import { BROWSER_POLL_MS } from "../../hooks/use-agent-browser";
import { vi } from "../../i18n/vi";
import { FakeBackend, coachAgent, fakeAgent } from "../../test/fake-backend";
import { type BrowserMachine, TAB_UNKNOWN, browserMachine, browserTab } from "../../test/fake-browser";
import { BrowserCard } from "./browser-card";

const t = vi.browser.card;
const READ = "/agents/coach/browser";
let backend: FakeBackend;
let opened: string[];

const main = browserTab({ id: 1, label: "main", idle_seconds: 40 });
const pay = browserTab({ id: 2, label: "pay", title: "Thanh toán", host: "pay.shop.example", idle_seconds: 3 });

afterEach(() => {
  vitest.useRealTimers();
  vitest.restoreAllMocks();
  vitest.unstubAllGlobals();
});

/** A crew whose coach asks for `mode`, on a machine that has a browser unless `machine` says otherwise. */
function crew(mode: BrowserMode = "act", machine: Partial<BrowserMachine> = {}) {
  backend = new FakeBackend();
  backend.agents = [fakeAgent, { ...coachAgent, browser: mode }];
  backend.browser.machine = browserMachine({ enabled: true, ...machine });
  opened = [];
  vitest.stubGlobal("fetch", backend.fetch);
  return backend.browser;
}

const card = (saved: BrowserMode | undefined, plain = false) => (
  <BrowserCard agentId="coach" savedMode={saved} onOpenConversation={plain ? undefined : (id) => opened.push(id)} />
);

/** The card as the coach's page draws it, the level being what the agent's file says. A
 *  `plain` page has no way to open a conversation. */
function show(options: { saved?: BrowserMode; plain?: boolean } = {}) {
  const saved = "saved" in options ? options.saved : backend.agents.find((a) => a.id === "coach")?.browser;
  return render(card(saved, options.plain));
}

const sent = () => backend.requests.map((r) => `${r.method} ${r.path}`);
const asked = () => sent().filter((line) => line === `GET ${READ}`).length;
/** Lets every answer on its way land, and what it draws be drawn. */
const settle = () => act(() => new Promise<void>((resolve) => setTimeout(resolve, 0)));
const shown = () => screen.queryByTestId("browser-card");
const state = () => screen.getByTestId("browser-state");
const activity = () => screen.getByTestId("browser-activity");
const row = (id: number) => within(screen.getByTestId(`browser-tab-${id}`));
const rows = () => screen.queryAllByTestId(/^browser-tab-/).map((li) => li.getAttribute("data-testid"));
const stopButton = () => screen.getByRole("button", { name: t.stop });
const closeButton = (label: string) => screen.getByRole("button", { name: t.closeTabNamed(label) });
const note = () => screen.getByTestId("browser-note");
/** The page is looked at again, or looked away from: the browser says which. */
const look = () =>
  act(() => {
    document.dispatchEvent(new Event("visibilitychange"));
  });

/** Only the page's own clock is the test's to turn; the waits of the test itself stay real. */
const clock = () => vitest.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
async function pass(ms: number) {
  act(() => {
    vitest.advanceTimersByTime(ms);
  });
  await settle();
}

/** Answers that can be kept on the wire: each is made up as the fake stood when it was asked,
 *  and lands when the test says, in the order the test says. */
function wire() {
  const held: { method: string; land: () => void }[] = [];
  let holding = false;
  vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const answer = await backend.fetch(input, init);
    if (holding) await new Promise<void>((land) => held.push({ method: init.method ?? "GET", land }));
    return answer;
  });
  return {
    hold: () => {
      holding = true;
    },
    waiting: () => held.map((one) => one.method),
    /** Lets one held answer land: the oldest, unless another is named by its place. */
    land: async (at = 0) => {
      held.splice(at, 1)[0].land();
      await settle();
    },
  };
}

describe("whether an agent's page has a browser card", () => {
  it("has none for an agent with no browser and none running", async () => {
    crew("off");
    show();
    await settle();

    expect(asked()).toBe(1);
    expect(shown()).not.toBeInTheDocument();
  });

  it("has one for an agent set to off whose browser is still up, so it can be stopped", async () => {
    crew("off").start("coach", [main]);
    show();

    expect(await screen.findByTestId("browser-card")).toBeInTheDocument();
    expect(state()).toHaveTextContent("Đang chạy · 1 tab");
    expect(stopButton()).toBeEnabled();
  });

  it("has none on a server older than the route, and asks it no more", async () => {
    crew().old = true;
    clock();
    show({ saved: undefined });
    await settle();

    expect(shown()).not.toBeInTheDocument();
    await pass(BROWSER_POLL_MS * 3);
    look();
    await settle();
    expect(asked()).toBe(1);
    expect(vitest.getTimerCount()).toBe(0);
  });

  it("has none for an agent the crew does not have, whatever level the page thinks it has", async () => {
    crew();
    backend.agents = [fakeAgent];
    clock();
    show({ saved: "act" });
    await settle();

    // A 404 is no failure to word: there is nothing here to read.
    expect(shown()).not.toBeInTheDocument();
    await pass(BROWSER_POLL_MS * 3);
    expect(asked()).toBe(1);
  });

  it("takes the card away once the route stops knowing the agent", async () => {
    crew().start("coach", [main]);
    clock();
    show();
    await settle();
    expect(shown()).toBeInTheDocument();

    backend.agents = [fakeAgent];
    await pass(BROWSER_POLL_MS);

    expect(shown()).not.toBeInTheDocument();
    await pass(BROWSER_POLL_MS * 2);
    expect(asked()).toBe(2);
  });

  it("is named, and stands as a section of its own", async () => {
    crew();
    show();

    const section = await screen.findByTestId("browser-card");
    expect(within(section).getByRole("heading", { name: vi.browser.title })).toBeInTheDocument();
    expect(section.tagName).toBe("SECTION");
  });
});

describe("where an agent's browser stands", () => {
  it("says the machine has the browser switched off", async () => {
    crew("act", { enabled: false });
    show();

    await screen.findByTestId("browser-card");
    expect(state()).toHaveTextContent(/^Máy này đang tắt trình duyệt, nên agent chưa mở được trang nào\.$/);
    expect(screen.queryByTestId("browser-activity")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("says the machine has no browser installed", async () => {
    crew("read", { installed: false, missing: "browser" });
    show();

    await screen.findByTestId("browser-card");
    expect(state()).toHaveTextContent(/^Máy này chưa cài trình duyệt\. Xem mục Kết nối\.$/);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("says the switch first on a machine that has both against it", async () => {
    crew("act", { enabled: false, installed: false, missing: "playwright" });
    show();

    await screen.findByTestId("browser-card");
    expect(state()).toHaveTextContent(t.machineOff);
    expect(state()).not.toHaveTextContent(t.notInstalled);
  });

  it("says a browser that is not up has not started, with nothing to stop", async () => {
    crew();
    show();

    await screen.findByTestId("browser-card");
    expect(state()).toHaveTextContent(t.stopped);
    expect(t.stopped).toMatch(/^Chưa chạy\./);
    expect(screen.queryByRole("button", { name: t.stop })).not.toBeInTheDocument();
    expect(screen.queryByRole("list", { name: t.tabs })).not.toBeInTheDocument();
    expect(screen.queryByTestId("browser-activity")).not.toBeInTheDocument();
  });

  it("says a browser that is up is running, with how many tabs and how long unused", async () => {
    crew().start("coach", [main, pay], { idleSeconds: 3 });
    show();

    await screen.findByTestId("browser-card");
    expect(state()).toHaveTextContent(/^Đang chạy · 2 tab$/);
    expect(activity()).toHaveTextContent(/^rảnh 3 giây$/);
    expect(screen.getByRole("list", { name: t.tabs })).toBeInTheDocument();
  });

  it("says it is working while a call is on it", async () => {
    crew().start("coach", [browserTab({ busy: true, idle_seconds: 0 })], { busy: true });
    show();

    await screen.findByTestId("browser-card");
    expect(activity()).toHaveTextContent(/^đang làm việc$/);
  });

  it("says a browser with no tab left is running all the same", async () => {
    crew().start("coach", [], { idleSeconds: 75 });
    show();

    await screen.findByTestId("browser-card");
    expect(state()).toHaveTextContent(/^Đang chạy · 0 tab$/);
    expect(activity()).toHaveTextContent(/^rảnh 1 phút$/);
    expect(screen.queryByRole("list", { name: t.tabs })).not.toBeInTheDocument();
    expect(stopButton()).toBeEnabled();
  });

  it.each([
    [0, "rảnh 0 giây"],
    [17, "rảnh 17 giây"],
    [59, "rảnh 59 giây"],
    [60, "rảnh 1 phút"],
    [185, "rảnh 3 phút"],
    [3600, "rảnh 60 phút"],
  ])("words %i idle seconds as %s", async (idleSeconds, words) => {
    crew().start("coach", [main], { idleSeconds });
    show();

    await screen.findByTestId("browser-card");
    expect(activity().textContent).toBe(words);
  });

  // The idle time moves at every read. Read aloud, it would speak every five seconds.
  it("announces the state and keeps the idle time out of what is announced", async () => {
    crew().start("coach", [main], { idleSeconds: 17 });
    show();

    await screen.findByTestId("browser-card");
    expect(state()).toHaveAttribute("role", "status");
    expect(state()).not.toHaveTextContent("rảnh");
    expect(activity().closest('[role="status"]')).toBeNull();
  });
});

describe("the tabs of a running browser", () => {
  it("are listed in the order the server gives them, whatever else they could be sorted by", async () => {
    crew();
    const answer: AgentBrowser = {
      mode: "act",
      enabled: true,
      installed: true,
      running: true,
      busy: false,
      idle_seconds: 5,
      tabs: [
        browserTab({ id: 2, label: "b", idle_seconds: 40 }),
        browserTab({ id: 3, label: "c", idle_seconds: 5 }),
        browserTab({ id: 1, label: "a", idle_seconds: 300 }),
      ],
    };
    vitest.stubGlobal("fetch", async () => Response.json(answer));
    show();

    await screen.findByTestId("browser-card");
    expect(rows()).toEqual(["browser-tab-2", "browser-tab-3", "browser-tab-1"]);
  });

  it("come last used first from a browser that is up", async () => {
    crew().start("coach", [main, pay, browserTab({ id: 3, label: "job", conversation_id: null, idle_seconds: 300 })]);
    show();

    await screen.findByTestId("browser-card");
    expect(rows()).toEqual(["browser-tab-2", "browser-tab-1", "browser-tab-3"]);
  });

  it("each say the name the agent gave it, what it shows, where, and how long it has sat", async () => {
    crew().start("coach", [browserTab({ id: 4, label: "pay", title: "Thanh toán", host: "pay.shop.example", idle_seconds: 185 })]);
    show();

    await screen.findByTestId("browser-card");
    expect(row(4).getByText("pay").tagName).toBe("CODE");
    expect(row(4).getByText("Thanh toán")).toBeInTheDocument();
    expect(row(4).getByText("pay.shop.example")).toBeInTheDocument();
    expect(row(4).getByText("rảnh 3 phút")).toBeInTheDocument();
    expect(row(4).queryByText(t.inUse)).not.toBeInTheDocument();
  });

  it("say a page with no title has none yet, and an empty tab is empty", async () => {
    crew().start("coach", [browserTab({ title: "", host: "" })]);
    show();

    await screen.findByTestId("browser-card");
    expect(row(1).getByText("(chưa có tiêu đề)")).toBeInTheDocument();
    expect(row(1).getByText("(trang trống)")).toBeInTheDocument();
  });

  it("say a tab a call is on is in use, not how long it has sat", async () => {
    crew().start("coach", [browserTab({ busy: true, idle_seconds: 0 })], { busy: true });
    show();

    await screen.findByTestId("browser-card");
    expect(row(1).getByText("đang dùng")).toBeInTheDocument();
    expect(row(1).queryByText(/rảnh/)).not.toBeInTheDocument();
  });

  it("open the conversation a tab belongs to", async () => {
    crew().start("coach", [browserTab({ conversation_id: "c7" })]);
    show();

    await screen.findByTestId("browser-card");
    const to = row(1).getByRole("button", { name: "Mở cuộc trò chuyện của tab main" });
    expect(to).toHaveTextContent(/^Mở cuộc trò chuyện$/);
    await userEvent.click(to);

    expect(opened).toEqual(["c7"]);
    // Going there closes nothing.
    expect(sent().filter((line) => !line.startsWith("GET"))).toEqual([]);
  });

  it("say a tab of a job belongs to scheduled work, with no conversation to open", async () => {
    crew().start("coach", [browserTab({ conversation_id: null })]);
    show();

    await screen.findByTestId("browser-card");
    expect(row(1).getByText("Việc theo lịch")).toBeInTheDocument();
    expect(row(1).queryByRole("button", { name: t.conversationOf("main") })).not.toBeInTheDocument();
  });

  it("say only that a tab is in a conversation on a page with no way to open one", async () => {
    crew().start("coach", [browserTab({ conversation_id: "c7" })]);
    show({ plain: true });

    await screen.findByTestId("browser-card");
    expect(row(1).getByText(t.inConversation)).toBeInTheDocument();
    expect(row(1).getAllByRole("button")).toEqual([closeButton("main")]);
  });

  it("each have a close button named after the tab", async () => {
    crew().start("coach", [main, pay]);
    show();

    await screen.findByTestId("browser-card");
    expect(row(1).getByRole("button", { name: "Đóng tab main" })).toHaveTextContent(/^Đóng tab$/);
    expect(row(2).getByRole("button", { name: "Đóng tab pay" })).toHaveTextContent(/^Đóng tab$/);
  });
});

describe("closing a tab", () => {
  it("happens at once: no question first, the request, then a fresh read", async () => {
    const browser = crew().start("coach", [main, pay]);
    const question = vitest.spyOn(window, "confirm");
    show();
    await screen.findByTestId("browser-tab-2");
    backend.requests.length = 0;

    await userEvent.click(closeButton("pay"));

    await waitFor(() => expect(rows()).toEqual(["browser-tab-1"]));
    expect(question).not.toHaveBeenCalled();
    expect(sent()).toEqual(["DELETE /agents/coach/browser/tabs/2", `GET ${READ}`]);
    expect(backend.requests[0].body).toBeNull();
    expect(browser.tabIds("coach")).toEqual([1]);
    expect(state()).toHaveTextContent(/^Đang chạy · 1 tab$/);
    expect(screen.queryByTestId("browser-note")).not.toBeInTheDocument();
    await waitFor(() => expect(closeButton("main")).toBeEnabled());
  });

  it("has every button wait from the press until the read after it has landed", async () => {
    crew().start("coach", [main, pay]);
    const line = wire();
    show();
    await screen.findByTestId("browser-tab-2");

    line.hold();
    await userEvent.click(closeButton("pay"));
    await waitFor(() => expect(line.waiting()).toEqual(["DELETE"]));
    expect(closeButton("pay")).toHaveTextContent(/^Đang đóng…$/);
    expect(closeButton("pay")).toBeDisabled();
    // The other tab's button waits and says what it does, not what the first is doing.
    expect(closeButton("main")).toHaveTextContent(/^Đóng tab$/);
    expect(closeButton("main")).toBeDisabled();
    expect(stopButton()).toBeDisabled();

    await line.land();
    // Closed on the server, and still drawn here: the read that takes it off is on its way.
    expect(line.waiting()).toEqual(["GET"]);
    expect(rows()).toEqual(["browser-tab-2", "browser-tab-1"]);
    expect(closeButton("pay")).toBeDisabled();
    expect(closeButton("main")).toBeDisabled();
    expect(stopButton()).toBeDisabled();

    await line.land();
    expect(rows()).toEqual(["browser-tab-1"]);
    expect(closeButton("main")).toBeEnabled();
    expect(stopButton()).toBeEnabled();
  });

  it("says a tab that was gone already in the server's own words, and shows the tabs there are", async () => {
    const browser = crew().start("coach", [main, pay]);
    show();
    await screen.findByTestId("browser-tab-2");
    // The agent closed it between the read and the press.
    browser.start("coach", [main]);
    backend.requests.length = 0;

    await userEvent.click(closeButton("pay"));

    await waitFor(() => expect(rows()).toEqual(["browser-tab-1"]));
    expect(note().textContent).toBe("Không còn tab này trong trình duyệt của agent.");
    expect(note().textContent).toBe(TAB_UNKNOWN);
    expect(note()).toHaveClass("warn");
    expect(note()).not.toHaveClass("danger");
    expect(note()).toHaveAttribute("role", "status");
    expect(sent()).toEqual(["DELETE /agents/coach/browser/tabs/2", `GET ${READ}`]);
    await waitFor(() => expect(closeButton("main")).toBeEnabled());
  });

  it("says a close the server refused the way the page's other failures are said, and keeps the tab", async () => {
    const browser = crew().start("coach", [main, pay]);
    browser.refuse.close = { status: 409, detail: "Trình duyệt đang bận." };
    show();
    await screen.findByTestId("browser-tab-2");

    await userEvent.click(closeButton("pay"));

    await waitFor(() => expect(note().textContent).toBe("Không được: Trình duyệt đang bận."));
    expect(note()).toHaveClass("danger");
    expect(rows()).toEqual(["browser-tab-2", "browser-tab-1"]);
    await waitFor(() => expect(closeButton("pay")).toBeEnabled());

    // The next press starts clean: what the last one said is not left beside it.
    browser.refuse.close = undefined;
    await userEvent.click(closeButton("pay"));
    await waitFor(() => expect(rows()).toEqual(["browser-tab-1"]));
    expect(screen.queryByTestId("browser-note")).not.toBeInTheDocument();
  });
});

describe("stopping the browser", () => {
  it("is offered with what stopping keeps, as the button's description", async () => {
    crew().start("coach", [main]);
    show();

    await screen.findByTestId("browser-card");
    expect(stopButton()).toHaveAccessibleDescription(t.stopNote);
    expect(t.stopNote).toContain("Đăng nhập vẫn được giữ");
    expect(stopButton()).toHaveClass("danger");
  });

  it("happens at once: no question first, the request, then a fresh read that says it is not up", async () => {
    const browser = crew().start("coach", [main, pay]);
    const question = vitest.spyOn(window, "confirm");
    show();
    await screen.findByTestId("browser-tab-2");
    backend.requests.length = 0;

    await userEvent.click(stopButton());

    await waitFor(() => expect(state()).toHaveTextContent(t.stopped));
    expect(question).not.toHaveBeenCalled();
    expect(sent()).toEqual(["POST /agents/coach/browser/stop", `GET ${READ}`]);
    expect(browser.running("coach")).toBe(false);
    expect(rows()).toEqual([]);
    // Nothing is left to stop or close; what is offered is the window to sign in through.
    expect(screen.getAllByRole("button").map((button) => button.textContent)).toEqual([vi.browser.login.start]);
    expect(screen.queryByTestId("browser-note")).not.toBeInTheDocument();
  });

  it("has every button wait from the press until the read after it has landed", async () => {
    crew().start("coach", [main, pay]);
    const line = wire();
    show();
    await screen.findByTestId("browser-tab-2");

    line.hold();
    await userEvent.click(stopButton());
    await waitFor(() => expect(line.waiting()).toEqual(["POST"]));
    const stopping = screen.getByRole("button", { name: "Đang dừng…" });
    expect(stopping).toBeDisabled();
    expect(closeButton("main")).toBeDisabled();
    expect(closeButton("pay")).toBeDisabled();
    expect(closeButton("pay")).toHaveTextContent(/^Đóng tab$/);

    await line.land();
    expect(line.waiting()).toEqual(["GET"]);
    expect(screen.getByRole("button", { name: "Đang dừng…" })).toBeDisabled();
    expect(closeButton("main")).toBeDisabled();

    await line.land();
    expect(state()).toHaveTextContent(t.stopped);
    expect(screen.getAllByRole("button").map((button) => button.textContent)).toEqual([vi.browser.login.start]);
  });

  it.each([
    [409, "Trình duyệt đang bận.", "Không được: Trình duyệt đang bận."],
    [500, "boom", `Không được: ${vi.requestErrors.server(500)}`],
  ])("says a stop the server refused with %i, and the browser is still there to stop", async (status, detail, said) => {
    const browser = crew().start("coach", [main]);
    browser.refuse.stop = { status, detail };
    show();
    await screen.findByTestId("browser-tab-1");

    await userEvent.click(stopButton());

    await waitFor(() => expect(note().textContent).toBe(said));
    expect(note()).toHaveClass("danger");
    expect(state()).toHaveTextContent(/^Đang chạy · 1 tab$/);
    await waitFor(() => expect(stopButton()).toBeEnabled());
    expect(browser.running("coach")).toBe(true);
  });
});

describe("reading the state again", () => {
  it("is done on opening, then every five seconds for as long as the page is looked at", async () => {
    const browser = crew();
    clock();
    show();
    await settle();
    expect(asked()).toBe(1);
    expect(state()).toHaveTextContent(t.stopped);

    await pass(BROWSER_POLL_MS - 1);
    expect(asked()).toBe(1);
    // The agent's first call brings its browser up, and nobody tells the page.
    browser.start("coach", [main]);
    await pass(1);
    expect(asked()).toBe(2);
    expect(state()).toHaveTextContent(/^Đang chạy · 1 tab$/);

    await pass(BROWSER_POLL_MS * 3);
    expect(asked()).toBe(5);
    expect(BROWSER_POLL_MS).toBe(5_000);
    // One clock, however many answers have been drawn.
    expect(vitest.getTimerCount()).toBe(1);
  });

  it("goes on for an agent with no card, whose browser a job may bring up", async () => {
    const browser = crew("off");
    clock();
    show();
    await settle();
    expect(shown()).not.toBeInTheDocument();

    // Left up by a turn that began before the level was set to off.
    browser.start("coach", [main]);
    await pass(BROWSER_POLL_MS);

    expect(state()).toHaveTextContent(/^Đang chạy · 1 tab$/);
  });

  it("is not done while the page is out of view, and is done at once when it is looked at again", async () => {
    const browser = crew();
    clock();
    show();
    await settle();

    const visibility = vitest.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    look();
    await settle();
    // Going out of view fires the same event as coming back: no read for a page nobody sees.
    expect(asked()).toBe(1);
    browser.start("coach", [main]);
    await pass(BROWSER_POLL_MS * 4);
    expect(asked()).toBe(1);
    expect(vitest.getTimerCount()).toBe(0);
    expect(state()).toHaveTextContent(t.stopped);

    visibility.mockReturnValue("visible");
    look();
    await settle();
    expect(asked()).toBe(2);
    expect(state()).toHaveTextContent(/^Đang chạy · 1 tab$/);
    // And the clock runs again: one of it, from now.
    expect(vitest.getTimerCount()).toBe(1);
    await pass(BROWSER_POLL_MS - 1);
    expect(asked()).toBe(2);
    await pass(1);
    expect(asked()).toBe(3);
  });

  it("is done once, with no clock, on a page opened out of view", async () => {
    crew();
    clock();
    vitest.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    show();
    await settle();

    expect(asked()).toBe(1);
    expect(vitest.getTimerCount()).toBe(0);
    await pass(BROWSER_POLL_MS * 2);
    expect(asked()).toBe(1);
  });

  it("ends with the page: no clock left, and nothing asked after it", async () => {
    crew();
    clock();
    const { unmount } = show();
    await settle();
    expect(vitest.getTimerCount()).toBe(1);

    unmount();

    expect(vitest.getTimerCount()).toBe(0);
    await pass(BROWSER_POLL_MS * 2);
    look();
    await settle();
    expect(asked()).toBe(1);
  });

  it("is done at once when a save changes the agent's level, which may have stopped the browser", async () => {
    const browser = crew("act").start("coach", [main]);
    const view = show();
    await screen.findByTestId("browser-tab-1");
    const before = asked();

    // What a save to off does on the server: the file says off, and the browser is stopped.
    backend.agents = [fakeAgent, { ...coachAgent, browser: "off" }];
    browser.saved("coach", "off");
    view.rerender(card("off"));

    await waitFor(() => expect(shown()).not.toBeInTheDocument());
    expect(asked()).toBe(before + 1);
  });

  it("is not done again for a page drawn again with the same level", async () => {
    crew().start("coach", [main]);
    const view = show();
    await screen.findByTestId("browser-tab-1");

    view.rerender(card("act"));
    await settle();

    expect(asked()).toBe(1);
  });
});

describe("answers that cross on the wire", () => {
  it("leave the newer one on screen when the older one lands after it", async () => {
    const browser = crew().start("coach", [main, pay]);
    const line = wire();
    show();
    await screen.findByTestId("browser-tab-2");

    line.hold();
    look();
    await waitFor(() => expect(line.waiting()).toHaveLength(1));
    // Asked with two tabs open; the agent closes one before the next read.
    browser.start("coach", [main]);
    look();
    await waitFor(() => expect(line.waiting()).toHaveLength(2));

    await line.land(1);
    expect(rows()).toEqual(["browser-tab-1"]);
    await line.land();
    expect(rows()).toEqual(["browser-tab-1"]);
    expect(state()).toHaveTextContent(/^Đang chạy · 1 tab$/);
  });

  it("draw each answer as it lands when they land in the order asked", async () => {
    const browser = crew().start("coach", [main, pay]);
    const line = wire();
    show();
    await screen.findByTestId("browser-tab-2");

    line.hold();
    look();
    await waitFor(() => expect(line.waiting()).toHaveLength(1));
    browser.start("coach", [main]);
    look();
    await waitFor(() => expect(line.waiting()).toHaveLength(2));

    await line.land();
    expect(rows()).toEqual(["browser-tab-2", "browser-tab-1"]);
    await line.land();
    expect(rows()).toEqual(["browser-tab-1"]);
  });

  it("do not bring back a tab closed here: a read asked before the press is not drawn after it", async () => {
    crew().start("coach", [main, pay]);
    const line = wire();
    show();
    await screen.findByTestId("browser-tab-2");

    line.hold();
    look();
    await waitFor(() => expect(line.waiting()).toEqual(["GET"]));
    await userEvent.click(closeButton("pay"));
    await waitFor(() => expect(line.waiting()).toEqual(["GET", "DELETE"]));
    await line.land(1);
    expect(line.waiting()).toEqual(["GET", "GET"]);
    // The read after the close lands first, then the one asked before it.
    await line.land(1);
    expect(rows()).toEqual(["browser-tab-1"]);
    await line.land();

    expect(rows()).toEqual(["browser-tab-1"]);
    expect(closeButton("main")).toBeEnabled();
  });
});

describe("a state that could not be read", () => {
  it("leaves what was shown and says so, until the next read that comes through", async () => {
    const browser = crew().start("coach", [main]);
    clock();
    show();
    await settle();

    browser.refuse.read = { status: 409, detail: "Máy chủ đang khởi động lại." };
    await pass(BROWSER_POLL_MS);
    expect(note().textContent).toBe("Không đọc được trạng thái trình duyệt: Máy chủ đang khởi động lại.");
    expect(note()).toHaveClass("danger");
    expect(note()).toHaveAttribute("role", "status");
    expect(state()).toHaveTextContent(/^Đang chạy · 1 tab$/);
    expect(rows()).toEqual(["browser-tab-1"]);

    browser.refuse.read = undefined;
    await pass(BROWSER_POLL_MS);
    expect(screen.queryByTestId("browser-note")).not.toBeInTheDocument();
    expect(state()).toHaveTextContent(/^Đang chạy · 1 tab$/);
  });

  it("is said on its own for an agent whose file asks for a browser, where a card was to be expected", async () => {
    crew("read").refuse.read = { status: 500, detail: "boom" };
    show();

    expect(await screen.findByTestId("browser-note")).toHaveTextContent(t.readFailed(vi.requestErrors.server(500)));
    expect(within(shown() as HTMLElement).getByRole("heading", { name: vi.browser.title })).toBeInTheDocument();
    expect(screen.queryByTestId("browser-state")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it.each([["off" as const], [undefined]])("is not said for an agent whose level is %s, which has no card to miss", async (saved) => {
    crew("off").refuse.read = { status: 500, detail: "boom" };
    show({ saved });
    await settle();

    expect(asked()).toBe(1);
    expect(shown()).not.toBeInTheDocument();
  });

  it("gives way to what an action has to say", async () => {
    const browser = crew().start("coach", [main, pay]);
    clock();
    show();
    await settle();
    browser.refuse.read = { status: 409, detail: "Máy chủ đang khởi động lại." };
    await pass(BROWSER_POLL_MS);
    expect(note()).toHaveTextContent("Không đọc được trạng thái trình duyệt");

    // The tab is gone on the server, and the read after the press fails like the one before.
    browser.start("coach", [main]);
    await userEvent.click(closeButton("pay"));
    await settle();

    expect(note().textContent).toBe(TAB_UNKNOWN);
  });
});
