// The window a person signs in through, on the agent's browser card: the three ways it is
// drawn, opening one and saying one is done, and how one that closes by itself is seen.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import type { BrowserLogin as Login } from "../../api/types";
import { type AgentBrowserController, BROWSER_POLL_MS } from "../../hooks/use-agent-browser";
import { vi } from "../../i18n/vi";
import {
  DONE, OPEN, READ, buttons, carried, clock, crew, doneButton, field, later, note, openButton, pass, saidAloud, sent, settle, show, state, wire,
} from "../../test/browser-card-screen";
import { browserTab } from "../../test/fake-browser";
import { LOGIN_LOCKED, URL_SCHEME } from "../../test/fake-browser-login";
import { BrowserLogin } from "./browser-login";

const t = vi.browser.card;
const OPEN_LINE = "Cửa sổ đăng nhập đang mở trên màn hình của máy chạy đội.";
const NOT_NOW = "Lúc này chưa mở được cửa sổ đăng nhập.";
const main = browserTab({ id: 1, label: "main" });

afterEach(() => {
  vitest.useRealTimers();
  vitest.restoreAllMocks();
  vitest.unstubAllGlobals();
});

const openLine = () => screen.queryByTestId("browser-login-open");
const why = () => screen.queryByTestId("browser-login-why");
const noField = () => expect(screen.queryByRole("textbox")).not.toBeInTheDocument();

describe("the sign-in window on an agent's browser card", () => {
  it("is offered where one can open: an address nobody has to give, the button, and what opening one does", async () => {
    crew();
    show();

    expect(await screen.findByRole("textbox", { name: "Địa chỉ mở sẵn (không bắt buộc)" })).toHaveValue("");
    expect(buttons()).toEqual(["Mở cửa sổ đăng nhập"]);
    expect(openButton()).toBeEnabled();
    expect(openButton()).toHaveAccessibleDescription(vi.browser.login.hint);
    for (const said of ["không phải trên thiết bị đang xem trang này", "trình duyệt của agent dừng và các tab của nó đóng", "tự đóng sau một lúc"])
      expect(vi.browser.login.hint).toContain(said);
    expect(saidAloud(screen.getByText(vi.browser.login.hint))).toBe(false);
    expect(openLine()).not.toBeInTheDocument();
    expect(why()).not.toBeInTheDocument();
    expect(state()).toHaveTextContent(t.stopped);
  });

  it("is shown open with the time it closes by itself on the viewer's clock, and the way to say one is done", async () => {
    const server = crew();
    server.browser.route(OPEN, "POST", {});
    show();

    // Opened at nine in Hanoi, for a quarter of an hour.
    expect(new Date().getTimezoneOffset()).toBe(-420);
    expect((await screen.findByTestId("browser-login-open")).textContent).toBe(`${OPEN_LINE} Tự đóng lúc 09:15.`);
    expect(openLine()).toHaveAttribute("role", "status");
    expect(buttons()).toEqual(["Xong"]);
    expect(doneButton()).toBeEnabled();
    noField();
    expect(why()).not.toBeInTheDocument();
  });

  it("says in the card's state line that the agent has no browser while the window is open", async () => {
    const server = crew();
    show();
    await screen.findByRole("textbox");
    expect(state().textContent).toBe(t.stopped);

    await userEvent.click(openButton());

    await waitFor(() => expect(state().textContent).toBe("Agent không dùng được trình duyệt trong lúc cửa sổ đăng nhập đang mở."));
    expect(server.browser.login.window("coach")).toEqual(later(15));
  });

  it("says what runs first where a browser is up beside an open window: it is still there to be stopped", async () => {
    const server = crew();
    server.browser.start("coach", [main]);
    // No server of today tells of both at once; the card is not to hide a browser if one does.
    vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const answer = await server.fetch(input, init);
      if ((init.method ?? "GET") !== "GET" || !String(input).endsWith(READ)) return answer;
      const body = await answer.json();
      return Response.json({ ...body, login: { ...body.login, open: true, until: later(15).toISOString() } });
    });
    show();

    await waitFor(() => expect(state().textContent).toBe(t.running(1)));
    expect(openLine()).toBeInTheDocument();
    expect(screen.getByRole("button", { name: t.stop })).toBeEnabled();
  });

  it.each([
    ["no_console", "Máy chủ của đội không chạy trong phiên màn hình nào đang mở, nên không có chỗ hiện cửa sổ đăng nhập."],
    ["locked", "Màn hình của máy đang khoá. Mở khoá thì mở được cửa sổ đăng nhập."],
    ["busy", "Agent đang dùng trình duyệt cho một lần gọi. Chờ lần gọi đó xong, hoặc dừng trình duyệt, rồi mở cửa sổ đăng nhập."],
  ])("has no field and no button to open one under %s, and says in one sentence what is in the way", async (word, said) => {
    const server = crew();
    if (word === "busy") server.browser.start("coach", [main], { busy: true });
    else server.browser.login.screen = word === "locked" ? "locked" : "none";
    show();

    expect((await screen.findByTestId("browser-login-why")).textContent).toBe(said);
    noField();
    expect(screen.queryByRole("button", { name: vi.browser.login.start })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: vi.browser.login.done })).not.toBeInTheDocument();
    expect(openLine()).not.toBeInTheDocument();
    // A call of the agent comes and goes at every read: the sentence is not said aloud each time.
    expect(saidAloud(why() as HTMLElement)).toBe(false);
  });

  it("says nothing of a window on a machine that gives the agent no browser, where the card says why already", async () => {
    crew({}, { enabled: false });
    show();

    expect(await screen.findByTestId("browser-state")).toHaveTextContent(t.machineOff);
    expect(why()).not.toBeInTheDocument();
    noField();
    expect(buttons()).toEqual([]);
    expect(screen.queryByText(NOT_NOW)).not.toBeInTheDocument();
  });

  it("says nothing of a window for an agent set to off whose browser is still up", async () => {
    crew({ browser: "off" }).browser.start("coach", [main]);
    show();

    await screen.findByTestId("browser-tab-1");
    expect(why()).not.toBeInTheDocument();
    noField();
    expect(buttons()).toEqual([t.closeTab, t.stop]);
  });

  it("is not drawn for a server that tells of no window, and the card is as it was", async () => {
    const server = crew();
    server.browser.login.old = true;
    show();

    expect(await screen.findByTestId("browser-state")).toHaveTextContent(t.stopped);
    expect(buttons()).toEqual([]);
    noField();
    expect(openLine()).not.toBeInTheDocument();
    expect(why()).not.toBeInTheDocument();
    expect(screen.queryByText(NOT_NOW)).not.toBeInTheDocument();
  });
});

describe("the sign-in window as a server may word it", () => {
  const still: AgentBrowserController = { browser: null, pending: null, note: null, stop: () => {}, closeTab: () => {}, openLogin: async () => true, closeLogin: () => {} };
  const drawn = (login: Partial<Login>) => render(<BrowserLogin login={{ open: false, until: null, available: false, why: "", ...login }} control={still} />);

  it("says an open window without a time where none is given", () => {
    drawn({ open: true });

    expect(openLine()?.textContent).toBe(OPEN_LINE);
  });

  it.each(["moon", "", "constructor", "toString"])("reads the word «%s», which it does not know, as not now", (word) => {
    drawn({ why: word });

    expect(why()?.textContent).toBe(NOT_NOW);
    noField();
    expect(buttons()).toEqual([]);
  });

  it("draws nothing at all for an agent with no browser", () => {
    const { container } = drawn({ why: "off" });

    expect(container).toBeEmptyDOMElement();
  });
});

describe("opening the sign-in window", () => {
  it("sends the address typed without the blanks around it, then reads the state again", async () => {
    const server = crew();
    show();
    await userEvent.type(await screen.findByRole("textbox"), "  https://shop.example/login ");
    server.requests.length = 0;

    await userEvent.click(openButton());

    expect(await screen.findByTestId("browser-login-open")).toBeInTheDocument();
    expect(sent()).toEqual([`POST ${OPEN}`, `GET ${READ}`]);
    expect(carried(OPEN)).toEqual([{ url: "https://shop.example/login" }]);
    expect(screen.queryByTestId("browser-note")).not.toBeInTheDocument();
  });

  it("sends an empty body where nothing was typed, and where only blanks were", async () => {
    const server = crew();
    show();
    await screen.findByRole("textbox");

    await userEvent.click(openButton());
    await userEvent.click(await screen.findByRole("button", { name: vi.browser.login.done }));
    await userEvent.type(await screen.findByRole("textbox"), "   ");
    await userEvent.click(openButton());

    await screen.findByTestId("browser-login-open");
    expect(carried(OPEN)).toEqual([{}, {}]);
    expect(server.browser.login.window("coach")).toBeDefined();
  });

  it("clears the field once a window opened on what was typed", async () => {
    crew();
    show();
    await userEvent.type(await screen.findByRole("textbox"), "https://shop.example/login");

    await userEvent.click(openButton());
    await userEvent.click(await screen.findByRole("button", { name: vi.browser.login.done }));

    expect(await screen.findByRole("textbox")).toHaveValue("");
  });

  it("stops the agent's browser: its tabs are gone from the card with the window open", async () => {
    const server = crew();
    server.browser.start("coach", [main]);
    show();
    await screen.findByTestId("browser-tab-1");

    await userEvent.click(openButton());

    await screen.findByTestId("browser-login-open");
    expect(screen.queryByTestId("browser-tab-1")).not.toBeInTheDocument();
    expect(buttons()).toEqual(["Xong"]);
    expect(server.browser.running("coach")).toBe(false);
  });

  it("shows a 422 as the server said it, as a warning, and keeps what was typed", async () => {
    const server = crew();
    show();
    await userEvent.type(await screen.findByRole("textbox"), "ftp://shop.example/tep");

    await userEvent.click(openButton());

    await waitFor(() => expect(note().textContent).toBe(URL_SCHEME));
    expect(note()).toHaveClass("warn");
    expect(note()).not.toHaveClass("danger");
    expect(field()).toHaveValue("ftp://shop.example/tep");
    await waitFor(() => expect(openButton()).toBeEnabled());
    expect(server.browser.login.window("coach")).toBeUndefined();
    expect(openLine()).not.toBeInTheDocument();
  });

  it("shows a 409 as the server said it, as a warning, and keeps what was typed for the next try", async () => {
    const server = crew();
    const failed = "Không mở được cửa sổ trình duyệt: hết bộ nhớ.";
    server.browser.refuse.login = { status: 409, detail: failed };
    show();
    await userEvent.type(await screen.findByRole("textbox"), "https://shop.example/login");

    await userEvent.click(openButton());

    await waitFor(() => expect(note().textContent).toBe(failed));
    expect(note()).toHaveClass("warn");
    expect(note()).not.toHaveClass("danger");
    expect(field()).toHaveValue("https://shop.example/login");

    // The next press starts clean, and sends what was kept.
    server.browser.refuse.login = undefined;
    await waitFor(() => expect(openButton()).toBeEnabled());
    await userEvent.click(openButton());
    await screen.findByTestId("browser-login-open");
    expect(screen.queryByTestId("browser-note")).not.toBeInTheDocument();
    expect(carried(OPEN)).toEqual([{ url: "https://shop.example/login" }, { url: "https://shop.example/login" }]);
  });

  it("keeps what was typed through a screen locked since the card was read, for when it is unlocked", async () => {
    const server = crew();
    clock();
    show();
    await settle();
    await userEvent.type(field(), "https://shop.example/login");
    server.browser.login.screen = "locked";

    await userEvent.click(openButton());

    // The server's sentence for the press, and under the card's own for the state it now reads.
    await waitFor(() => expect(note().textContent).toBe(LOGIN_LOCKED));
    expect(note()).toHaveClass("warn");
    expect(why()).toHaveTextContent("Màn hình của máy đang khoá.");
    noField();

    server.browser.login.screen = "open";
    await pass(BROWSER_POLL_MS);
    expect(field()).toHaveValue("https://shop.example/login");
  });

  it.each([
    [500, "boom", vi.requestErrors.server(500)],
    [403, "Không có quyền.", "Không có quyền."],
  ])("says any other failure, a %i, as the card's usual note, and keeps what was typed", async (status, detail, worded) => {
    const server = crew();
    server.browser.refuse.login = { status, detail };
    show();
    await userEvent.type(await screen.findByRole("textbox"), "https://shop.example/login");

    await userEvent.click(openButton());

    await waitFor(() => expect(note().textContent).toBe(`Không được: ${worded}`));
    expect(note()).toHaveClass("danger");
    expect(note()).not.toHaveClass("warn");
    expect(field()).toHaveValue("https://shop.example/login");
    expect(openLine()).not.toBeInTheDocument();
  });
});

describe("saying one is done with the sign-in window", () => {
  it("closes it, reads the state again, and the way to open one is back", async () => {
    const server = crew();
    server.browser.route(OPEN, "POST", {});
    show();
    await screen.findByTestId("browser-login-open");
    server.requests.length = 0;

    await userEvent.click(doneButton());

    await waitFor(() => expect(buttons()).toEqual(["Mở cửa sổ đăng nhập"]));
    expect(sent()).toEqual([`POST ${DONE}`, `GET ${READ}`]);
    expect(server.browser.login.window("coach")).toBeUndefined();
    expect(openLine()).not.toBeInTheDocument();
    expect(state().textContent).toBe(t.stopped);
    expect(screen.queryByTestId("browser-note")).not.toBeInTheDocument();
  });

  it("says nothing when the window had closed by itself before the press", async () => {
    const server = crew();
    server.browser.route(OPEN, "POST", {});
    show();
    await screen.findByTestId("browser-login-open");
    // A quarter of an hour on, with no read between: the card still shows it open.
    server.browser.login.now = () => later(15, 1);
    expect(server.browser.login.window("coach")).toBeUndefined();

    await userEvent.click(doneButton());

    await waitFor(() => expect(buttons()).toEqual(["Mở cửa sổ đăng nhập"]));
    expect(sent()).toContain(`POST ${DONE}`);
    expect(screen.queryByTestId("browser-note")).not.toBeInTheDocument();
  });

  it.each([
    [500, "boom", vi.requestErrors.server(500)],
    [409, "Cửa sổ chưa đóng được.", "Cửa sổ chưa đóng được."],
  ])("says a done the server refused with %i as a failure, and the window is still there to close", async (status, detail, worded) => {
    const server = crew();
    server.browser.route(OPEN, "POST", {});
    server.browser.refuse.done = { status, detail };
    show();
    await screen.findByTestId("browser-login-open");

    await userEvent.click(doneButton());

    await waitFor(() => expect(note().textContent).toBe(`Không được: ${worded}`));
    expect(note()).toHaveClass("danger");
    expect(openLine()).toBeInTheDocument();
    await waitFor(() => expect(doneButton()).toBeEnabled());
  });
});

describe("the card's buttons while a request for the sign-in window is in flight", () => {
  it("all wait from the press that opens one until the read after it has landed", async () => {
    crew().browser.start("coach", [main]);
    const line = wire();
    show();
    await screen.findByTestId("browser-tab-1");

    line.hold();
    await userEvent.click(openButton());
    await waitFor(() => expect(line.waiting()).toEqual(["POST"]));
    expect(buttons()).toEqual([t.closeTab, t.stop, "Đang mở…"]);
    for (const button of screen.getAllByRole("button")) expect(button).toBeDisabled();

    await line.land();
    expect(line.waiting()).toEqual(["GET"]);
    expect(buttons()).toEqual([t.closeTab, t.stop, "Đang mở…"]);
    for (const button of screen.getAllByRole("button")) expect(button).toBeDisabled();

    await line.land();
    expect(buttons()).toEqual(["Xong"]);
    expect(doneButton()).toBeEnabled();
  });

  it("all wait from the press that closes one until the read after it has landed", async () => {
    const server = crew();
    server.browser.route(OPEN, "POST", {});
    const line = wire();
    show();
    await screen.findByTestId("browser-login-open");

    line.hold();
    await userEvent.click(doneButton());
    await waitFor(() => expect(line.waiting()).toEqual(["POST"]));
    expect(buttons()).toEqual(["Đang đóng…"]);
    expect(screen.getByRole("button")).toBeDisabled();

    await line.land();
    expect(line.waiting()).toEqual(["GET"]);
    expect(screen.getByRole("button", { name: "Đang đóng…" })).toBeDisabled();

    await line.land();
    expect(buttons()).toEqual(["Mở cửa sổ đăng nhập"]);
    expect(openButton()).toBeEnabled();
  });

  it("wait too while the browser is being stopped or a tab closed, and read as they did", async () => {
    crew().browser.start("coach", [main, browserTab({ id: 2, label: "pay" })]);
    const line = wire();
    show();
    await screen.findByTestId("browser-tab-2");

    line.hold();
    await userEvent.click(screen.getByRole("button", { name: t.closeTabNamed("pay") }));
    await waitFor(() => expect(line.waiting()).toEqual(["DELETE"]));
    expect(openButton()).toBeDisabled();
    await line.land();
    await line.land();
    expect(openButton()).toBeEnabled();

    await userEvent.click(screen.getByRole("button", { name: t.stop }));
    await waitFor(() => expect(line.waiting()).toEqual(["POST"]));
    expect(openButton()).toBeDisabled();
    await line.land();
    await line.land();
    expect(buttons()).toEqual(["Mở cửa sổ đăng nhập"]);
    expect(openButton()).toBeEnabled();
  });
});

describe("a sign-in window nobody on this page opened or closed", () => {
  it("is gone from the card at the next read once it closed by itself, with no request of its own", async () => {
    const server = crew();
    server.browser.route(OPEN, "POST", {});
    clock();
    show();
    await settle();
    expect(openLine()).toBeInTheDocument();

    // A second short of its time it is still there.
    server.browser.login.now = () => later(14, 59);
    await pass(BROWSER_POLL_MS);
    expect(openLine()).toBeInTheDocument();
    server.requests.length = 0;

    server.browser.login.now = () => later(15, 1);
    await pass(BROWSER_POLL_MS - 1);
    expect(openLine()).toBeInTheDocument();
    await pass(1);

    expect(openLine()).not.toBeInTheDocument();
    expect(buttons()).toEqual(["Mở cửa sổ đăng nhập"]);
    expect(state().textContent).toBe(t.stopped);
    expect(sent()).toEqual([`GET ${READ}`]);
  });

  it("is shown at the next read once it was opened from another page", async () => {
    const server = crew();
    clock();
    show();
    await settle();
    expect(buttons()).toEqual(["Mở cửa sổ đăng nhập"]);

    server.browser.route(OPEN, "POST", {});
    await pass(BROWSER_POLL_MS);

    expect(openLine()?.textContent).toBe(`${OPEN_LINE} Tự đóng lúc 09:15.`);
    expect(buttons()).toEqual(["Xong"]);
  });
});
