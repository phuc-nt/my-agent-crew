// The window a person signs in through on an agent's browser, and the hosts that browser may
// still be signed in to, as a person meets them on the agent's page.
import { expect, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeBrowser, browserMachine, browserTab } from "../src/test/fake-browser";
import { URL_SCHEME } from "../src/test/fake-browser-login";
import { coachAgent, defaultAgent, mockApi } from "./mock-api";
import { smallTargets } from "./small-targets";
import { spills } from "./spills";

const t = vi.browser;
const master = { ...defaultAgent, name: "Trợ lý", delegates: ["coach"] };
const coach = (rest: object = {}) => ({ ...coachAgent, browser: "act", declared: { delegates: [], schedules: [], tools: [] }, ...rest });
/** Nine in the morning in Hanoi, where the page's clock is. */
const NINE = new Date("2026-10-14T02:00:00Z");
/** Half past midnight on the twelfth of November there. */
const NOVEMBER = new Date("2026-11-11T17:30:00Z");

/** A machine that has a browser to start and a screen to show a window on, its clock at nine. */
function machine() {
  const browser = Object.assign(new FakeBrowser(), { machine: browserMachine({ enabled: true }) });
  browser.login.now = () => NINE;
  return browser;
}
/** This many hosts that each hold a sign-in, after `first`. */
const held = (count: number, first: string[] = []) =>
  Object.fromEntries([...first, ...Array.from({ length: count }, (_, at) => `h${String(at + 1).padStart(2, "0")}.example`)].map((host) => [host, NOVEMBER]));

const pageWidth = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth);
const posted = (page: Page, path: RegExp) => page.waitForRequest((r) => r.method() === "POST" && path.test(r.url()));
const READ = /\/api\/agents\/coach\/browser$/;
const OPEN = /\/api\/agents\/coach\/browser\/login$/;
const DONE = /\/api\/agents\/coach\/browser\/login\/done$/;

const ADDRESS = "Địa chỉ mở sẵn (không bắt buộc)";
const START = "Mở cửa sổ đăng nhập";
const HOSTS = "Có thể đang đăng nhập ở";

test("behind a locked screen the card has no way to open a sign-in window and says why; unlocked, it offers one at its next read", async ({ page }) => {
  const browser = machine();
  browser.login.screen = "locked";
  await mockApi(page, { agents: [master, coach()], browser });
  await page.goto("/#/manage/crew/coach");
  const card = page.getByTestId("browser-card");

  await expect(card.getByTestId("browser-login-why")).toHaveText("Màn hình của máy đang khoá. Mở khoá thì mở được cửa sổ đăng nhập.");
  await expect(card.getByTestId("browser-state")).toHaveText(t.card.stopped);
  await expect(card.getByRole("button")).toHaveCount(0);
  await expect(card.getByRole("textbox")).toHaveCount(0);

  // Nobody tells the page the screen was unlocked: its own clock reads it.
  browser.login.screen = "open";
  await expect(card.getByRole("button", { name: START })).toBeVisible({ timeout: 10_000 });
  await expect(card.getByRole("textbox", { name: ADDRESS })).toHaveValue("");
  await expect(card.getByTestId("browser-login-why")).toHaveCount(0);
});

test("a sign-in window opens on the address typed, says when it closes by itself, and is closed with one press", async ({ page }) => {
  const browser = machine().start("coach", [browserTab()]);
  await mockApi(page, { agents: [master, coach()], browser });
  await page.goto("/#/manage/crew/coach");
  const card = page.getByTestId("browser-card");
  const state = card.getByTestId("browser-state");
  const address = card.getByRole("textbox", { name: ADDRESS });
  const start = card.getByRole("button", { name: START });

  await expect(state).toHaveText(t.card.running(1));
  await expect(start).toHaveAccessibleDescription(t.login.hint);
  await address.fill("  https://shop.example/login ");
  const opened = posted(page, OPEN);
  await start.click();
  expect((await opened).postDataJSON()).toEqual({ url: "https://shop.example/login" });

  await expect(card.getByTestId("browser-login-open")).toHaveText("Cửa sổ đăng nhập đang mở trên màn hình của máy chạy đội. Tự đóng lúc 09:15.");
  await expect(state).toHaveText("Agent không dùng được trình duyệt trong lúc cửa sổ đăng nhập đang mở.");
  // The agent's browser stopped for it: its tabs are gone, and with them the way to stop it.
  await expect(card.getByRole("list", { name: t.card.tabs })).toHaveCount(0);
  await expect(card.getByRole("button")).toHaveText(["Xong"]);
  expect(browser.running("coach")).toBe(false);

  const closed = posted(page, DONE);
  await card.getByRole("button", { name: "Xong" }).click();
  await closed;
  await expect(start).toBeEnabled();
  await expect(address).toHaveValue("");
  await expect(card.getByTestId("browser-login-open")).toHaveCount(0);
  await expect(state).toHaveText(t.card.stopped);
  await expect(card.getByTestId("browser-note")).toHaveCount(0);
  expect(browser.login.window("coach")).toBeUndefined();
  // Nothing of it was a change to the agent's file.
  await expect(page.getByTestId("agent-editor").getByText(vi.editor.clean)).toBeVisible();
});

test("a sign-in window opens with no address given, on a request that carries none", async ({ page }) => {
  await mockApi(page, { agents: [master, coach()], browser: machine() });
  await page.goto("/#/manage/crew/coach");
  const card = page.getByTestId("browser-card");

  const opened = posted(page, OPEN);
  await card.getByRole("button", { name: START }).click();
  expect((await opened).postDataJSON()).toEqual({});
  await expect(card.getByRole("button", { name: "Xong" })).toBeVisible();
});

test("an address the crew's browser does not go to is refused in the server's own sentence, and stays in the field", async ({ page }) => {
  const browser = machine();
  await mockApi(page, { agents: [master, coach()], browser });
  await page.goto("/#/manage/crew/coach");
  const card = page.getByTestId("browser-card");
  const address = card.getByRole("textbox", { name: ADDRESS });
  const start = card.getByRole("button", { name: START });

  // A host with no scheme is what a person types first.
  await address.fill("shop.example/login");
  await start.click();

  const note = card.getByTestId("browser-note");
  await expect(note).toHaveText(URL_SCHEME);
  await expect(note).toHaveClass(/\bwarn\b/);
  await expect(note).not.toHaveClass(/\bdanger\b/);
  await expect(address).toHaveValue("shop.example/login");
  await expect(start).toBeEnabled();
  await expect(card.getByTestId("browser-login-open")).toHaveCount(0);
  expect(browser.login.window("coach")).toBeUndefined();

  // Corrected, the same press opens it and the note is gone.
  await address.fill("https://shop.example/login");
  await start.click();
  await expect(card.getByTestId("browser-login-open")).toBeVisible();
  await expect(note).toHaveCount(0);
});

test("the hosts of an agent's own list are each shown, with the day its sign-in runs out or as holding none", async ({ page }) => {
  const browser = machine();
  browser.login.signedIn("coach", { "pay.shop.example": NOVEMBER, "elsewhere.example": NOVEMBER });
  const hosts = ["shop.example", "*.track.example", ...Object.keys(held(8))];
  await mockApi(page, { agents: [master, coach({ browser_hosts: hosts })], browser });
  await page.goto("/#/manage/crew/coach");
  const card = page.getByTestId("browser-card");
  const chips = card.getByRole("list", { name: HOSTS }).getByRole("listitem");

  // Every host of the file, in its order, though there are more than an agent with no list is shown.
  await expect(chips).toHaveCount(10);
  await expect(chips.nth(0)).toHaveText("shop.example · đến 12/11/2026");
  await expect(chips.nth(1)).toHaveText("*.track.example · chưa thấy đăng nhập");
  await expect(chips.nth(0)).not.toHaveClass(/\bmuted\b/);
  await expect(chips.nth(1)).toHaveClass(/\bmuted\b/);
  await expect(card.getByRole("button", { name: /máy chủ nữa$/ })).toHaveCount(0);
  await expect(card.getByText(t.signedIn.caveat)).toBeVisible();
  await expect(card.getByText("elsewhere.example")).toHaveCount(0);
});

test("an agent with no list of its own is shown eight of the hosts its browser holds, and the rest at one press", async ({ page }) => {
  const browser = machine();
  browser.login.signedIn("coach", held(11));
  await mockApi(page, { agents: [master, coach()], browser });
  await page.goto("/#/manage/crew/coach");
  const card = page.getByTestId("browser-card");
  const list = card.getByRole("list", { name: HOSTS });
  const more = card.getByRole("button", { name: "+3 máy chủ nữa" });

  await expect(list.getByRole("listitem")).toHaveCount(8);
  await expect(list.getByRole("listitem").last()).toHaveText("h08.example · đến 12/11/2026");
  await more.click();

  await expect(list.getByRole("listitem")).toHaveCount(11);
  // Gone under any count, not left behind as a button for no host at all.
  await expect(card.getByRole("button", { name: /máy chủ nữa$/ })).toHaveCount(0);
  // The button the press was on is gone: the keyboard is on the list it filled.
  await expect(list).toBeFocused();
});

test("a browser that holds no sign-in says so in one sentence, and a profile no browser closed on says nothing", async ({ page }) => {
  const browser = machine();
  await mockApi(page, { agents: [master, coach()], browser });
  await page.goto("/#/manage/crew/coach");
  const card = page.getByTestId("browser-card");

  await expect(card.getByRole("button", { name: START })).toBeVisible();
  await expect(card.getByTestId("browser-signed-in-none")).toHaveCount(0);
  await expect(card.getByText(t.signedIn.caveat)).toHaveCount(0);

  // The agent's first call starts its browser, which has cookies for nowhere yet.
  browser.start("coach", [browserTab()]);
  await expect(card.getByTestId("browser-signed-in-none")).toHaveText("Chưa thấy đăng nhập ở máy chủ nào.", { timeout: 10_000 });
  await expect(card.getByRole("list", { name: HOSTS })).toHaveCount(0);
});

test("a server from before the sign-in window has the card as it was: neither the window nor the hosts", async ({ page }) => {
  const browser = machine().start("coach", [browserTab()]);
  browser.login.old = true;
  browser.login.signedIn("coach", { "shop.example": NOVEMBER });
  await mockApi(page, { agents: [master, coach({ browser_hosts: ["shop.example"] })], browser });
  const read = page.waitForResponse((r) => r.status() === 200 && READ.test(r.url()));
  await page.goto("/#/manage/crew/coach");
  const told = await (await read).json();
  expect(told).not.toHaveProperty("login");
  expect(told).not.toHaveProperty("logins");
  const card = page.getByTestId("browser-card");

  await expect(card.getByTestId("browser-state")).toHaveText(t.card.running(1));
  await expect(card.getByRole("button", { name: t.card.stop })).toBeVisible();
  await expect(card.getByRole("textbox")).toHaveCount(0);
  await expect(card.getByRole("button", { name: START })).toHaveCount(0);
  await expect(card.getByTestId("browser-login-why")).toHaveCount(0);
  await expect(card.getByText(HOSTS)).toHaveCount(0);
  await expect(card.getByText(t.signedIn.none)).toHaveCount(0);
  await expect(card.getByText(t.signedIn.caveat)).toHaveCount(0);
  await expect(page.locator(".crash")).toHaveCount(0);

  // Its catalogue has the six tools of that release.
  await page.goto("/#/manage/tools");
  const matrix = page.getByTestId("tools-matrix");
  await expect(matrix.getByText(t.withBrowser)).toHaveCount(6);
  await expect(matrix.getByText("browser_download")).toHaveCount(0);
  await expect(matrix.getByText("browser_pdf")).toHaveCount(0);
  await expect(page.locator(".crash")).toHaveCount(0);
});

test.describe("on a phone", () => {
  // A touch screen at the width people hold.
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  // What a cookie names has nowhere to break at: no space, and no hyphen either.
  const LONG_HOST = "d3b07384d113edec49eaa6238ad5ff00c1f169fbd61e9b5bb2f0a7c8.cdn.shop.example";
  const CARD = '[data-testid="browser-card"]';

  test("the way to open a sign-in window and the hosts stay inside the page, with every control big enough for a finger", async ({ page }) => {
    const browser = machine();
    browser.login.signedIn("coach", held(10, [LONG_HOST]));
    await mockApi(page, { agents: [master, coach()], browser });
    await page.goto("/#/manage/crew/coach");
    const card = page.getByTestId("browser-card");
    const address = card.getByRole("textbox", { name: ADDRESS });
    const chips = card.getByRole("list", { name: HOSTS }).getByRole("listitem");
    const more = card.getByRole("button", { name: "+3 máy chủ nữa" });

    await expect(card.getByRole("button", { name: START })).toBeVisible();
    await expect(chips).toHaveCount(8);
    await expect(chips.first()).toContainText(LONG_HOST);
    await expect(more).toBeVisible();

    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
    expect(await spills(page, CARD)).toEqual([]);
    expect(await smallTargets(page, CARD)).toEqual([]);
    // Safari zooms the page into any field under 16px when it takes focus.
    expect(await address.evaluate((el) => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16);
    expect((await address.boundingBox())!.height).toBeGreaterThanOrEqual(40);

    // An address longer than the field scrolls inside it, and the page is no wider for it.
    await address.fill(`https://${LONG_HOST}/dang-nhap?tiep=/don-hang/20261013`);
    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
    const box = (await address.boundingBox())!;
    expect(box.x + box.width).toBeLessThanOrEqual(390);

    await address.fill("");
    await more.click();
    await expect(chips).toHaveCount(11);
    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
    expect(await spills(page, CARD)).toEqual([]);
  });

  test("an open sign-in window, and what is in the way of one, wrap inside the page", async ({ page }) => {
    const browser = machine();
    browser.login.signedIn("coach", {});
    await mockApi(page, { agents: [master, coach({ browser_hosts: ["shop.example", `*.${LONG_HOST}`] })], browser });
    await page.goto("/#/manage/crew/coach");
    const card = page.getByTestId("browser-card");

    await card.getByRole("button", { name: START }).click();
    await expect(card.getByTestId("browser-login-open")).toContainText("Tự đóng lúc 09:15.");
    await expect(card.getByRole("list", { name: HOSTS }).getByRole("listitem")).toHaveCount(2);
    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
    expect(await spills(page, CARD)).toEqual([]);
    expect(await smallTargets(page, CARD)).toEqual([]);

    await card.getByRole("button", { name: "Xong" }).click();
    await expect(card.getByRole("button", { name: START })).toBeVisible();
    browser.login.screen = "none";
    await expect(card.getByTestId("browser-login-why")).toHaveText(t.login.why.no_console, { timeout: 10_000 });
    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
    expect(await spills(page, CARD)).toEqual([]);
  });
});
