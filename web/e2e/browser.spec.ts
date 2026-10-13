// An agent's browser as a person meets it on the page: what the machine has, on the
// connections page; the agent's own setting and what it has running, on its page; a call
// that waits, said in a line; and the picture a screenshot saved, small where its call is.
import { expect, type Locator, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeBrowser, browserMachine, browserTab } from "../src/test/fake-browser";
import { type Conversation, coachAgent, defaultAgent, mockApi, run } from "./mock-api";
import { smallTargets } from "./small-targets";
import { spills } from "./spills";

const t = vi.browser;
const master = { ...defaultAgent, name: "Trợ lý", delegates: ["coach"] };
const coach = (rest: object = {}) => ({ ...coachAgent, declared: { delegates: [], schedules: [], tools: [] }, ...rest });
/** A machine that has a browser to start, with the browsers a test says are up. */
const machineOn = () => Object.assign(new FakeBrowser(), { machine: browserMachine({ enabled: true }) });

const pageWidth = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth);
const top = async (of: Locator) => (await of.boundingBox())!.y;

const REASON = "máy chủ shop.example chưa có trong danh sách của agent";
const SHOT = "screenshots/20261013T120000Z-don.png";
const GONE = "screenshots/20261013T120500Z-gio.png";
const WHOLE_PAGE = "screenshots/20261013T121000Z-ca-trang.png";
const fileUrl = (path: string) => `/api/agents/coach/files?path=${encodeURIComponent(path)}`;

/** A conversation of the coach's, paused on one call that waits for a person. */
function paused(id: string, title: string, tool_name: string, args: Record<string, unknown>, reason?: string): Conversation {
  const call = { id: "tc", name: tool_name, arguments: args };
  return {
    id, agent_id: "coach", channel: "", title, summary: "", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "awaiting_approval", over_budget: false, parent_call_id: "",
    messages: [{ id: "m1", seq: 1, role: "assistant", content: "", tool_calls: [call], tool_call_id: null, name: null, provider: null, model: null, cost_usd: null, created_at: "" }],
    pending_approval: {
      id: "ap", conversation_id: id, message_id: "m1", tool_call_id: "tc", tool_name, arguments: args, status: "pending", created_at: "",
      expires_at: new Date(Date.now() + 5 * 60_000).toISOString(), resolved_at: null, kind: "tool", ...(reason ? { reason } : {}),
    },
  };
}
const waiting = (conversationId: string) =>
  run({ id: `wait-${conversationId}`, agent_id: "coach", conversation_id: conversationId, status: "awaiting_approval", finished_at: null, summary: "" });

/** The step a run keeps of a screenshot: the tool's first line names the tab and the file. */
const shot = (id: string, label: string, path: string) => ({
  kind: "tool", name: "browser_screenshot", tool_call_id: id, arguments: { tab: label }, ok: true,
  output: `Đã lưu ảnh chụp tab ${label} vào ${path}. Kích thước 1280x720, 48 KB.`, duration_ms: 420,
});

test("the connections page says which browser the machine has and whose is up, and sets nothing", async ({ page }) => {
  const browser = machineOn().start("coach", [browserTab()]);
  await mockApi(page, { agents: [master, coach({ browser: "act" })], browser });
  await page.goto("/#/manage/connections");

  const card = page.getByTestId("browser-machine");
  await expect(card.getByRole("heading", { name: t.title })).toBeVisible();
  const state = card.getByTestId("browser-machine-state");
  await expect(state).toContainText(t.machine.on);
  await expect(state).toContainText(t.machine.channel.chromium);
  await expect(state).toContainText("141.0.7390.37");
  await expect(card.getByTestId("browser-machine-running")).toHaveText("Đang chạy cho 1 agent: HLV sức khoẻ");
  await expect(card.getByTestId("browser-missing")).toHaveCount(0);
  // The switch is the machine's own file: the card has nothing to press or fill.
  await expect(card.locator("button, input, select, textarea, a")).toHaveCount(0);
});

test("the connections page says a browser is switched off, or what is missing and the command that installs it", async ({ page }) => {
  const browser = new FakeBrowser();
  await mockApi(page, { agents: [master, coach()], browser });
  await page.goto("/#/manage/connections");

  const card = page.getByTestId("browser-machine");
  await expect(card.getByTestId("browser-machine-state")).toHaveText(t.machine.off);
  await expect(card.getByTestId("browser-machine-running")).toHaveText(t.machine.noneRunning);

  browser.machine = browserMachine({ enabled: true, installed: false, version: "", missing: "browser", install_command: "uv run playwright install chromium" });
  await page.reload();
  await expect(card.getByTestId("browser-machine-state")).toContainText(t.machine.on);
  await expect(card.getByTestId("browser-missing")).toContainText(t.machine.missingChromium);
  await expect(card.getByTestId("browser-missing").locator("code")).toHaveText("uv run playwright install chromium");
});

test("the connections page keeps whose browser is up current with no reload: after a stop on the agent's page, and as one comes up", async ({ page }) => {
  const browser = machineOn().start("coach", [browserTab()]);
  await mockApi(page, { agents: [master, coach({ browser: "act" })], browser });
  // The manage screen reads the machine once, here, while the coach's browser is up.
  await page.goto("/#/manage/crew/coach");
  const own = page.getByTestId("browser-card");
  await own.getByRole("button", { name: t.card.stop }).click();
  await expect(own.getByTestId("browser-state")).toHaveText(t.card.stopped);

  await page.getByRole("navigation", { name: vi.manage.nav }).getByRole("button", { name: vi.manage.connections }).click();
  const running = page.getByTestId("browser-machine").getByTestId("browser-machine-running");
  await expect(running).toHaveText(t.machine.noneRunning);

  // The agent's next call brings its browser up, and nobody tells the page: its own clock does.
  browser.start("coach", [browserTab()]);
  await expect(running).toHaveText("Đang chạy cho 1 agent: HLV sức khoẻ", { timeout: 10_000 });
});

test("an agent's browser level and its hosts are set, saved as two keys, and still there after a reload", async ({ page }) => {
  await mockApi(page, { agents: [master, coach()], browser: machineOn() });
  await page.goto("/#/manage/crew/coach");
  const editor = page.getByTestId("agent-editor");
  const tools = editor.getByTestId("section-tools");
  const mode = tools.getByRole("combobox", { name: t.mode });
  const hosts = tools.getByRole("textbox", { name: t.hosts });
  const save = editor.getByRole("button", { name: vi.editor.save, exact: true });

  // As the crew runs an agent whose file says nothing of a browser.
  await expect(mode).toHaveValue("off");
  await expect(mode).toHaveAccessibleDescription(t.modeHint.off);
  await expect(hosts).toHaveCount(0);
  await expect(tools.getByText(t.outsideList)).toBeVisible();
  await expect(page.getByTestId("browser-card")).toHaveCount(0);
  await expect(save).toBeDisabled();

  await mode.selectOption("read");
  await expect(mode).toHaveAccessibleDescription(t.modeHint.read);
  await expect(hosts).toHaveAccessibleDescription(t.hostsHint);
  await expect(tools.getByTestId("browser-machine-warning")).toHaveCount(0);

  // An address is not a host: the line is named under the box, and the save waits for it.
  await hosts.fill("https://shop.example/cart");
  await expect(tools.getByText(t.hostInvalid("https://shop.example/cart"))).toBeVisible();
  await expect(save).toBeDisabled();

  await hosts.fill("Shop.Example\n\n  *.cdn.shop.example  \n");
  await expect(tools.getByText(/không phải tên máy chủ/)).toHaveCount(0);
  const patch = page.waitForRequest((r) => r.method() === "PATCH" && /\/api\/agents\/coach$/.test(r.url()));
  await save.click();
  expect((await patch).postDataJSON()).toEqual({ profile: { browser: "read", browser_hosts: ["shop.example", "*.cdn.shop.example"] } });
  await expect(editor.getByText(vi.editor.clean)).toBeVisible();
  // The agent now has a browser, which nothing has started yet.
  await expect(page.getByTestId("browser-state")).toHaveText(t.card.stopped);

  await page.reload();
  await expect(mode).toHaveValue("read");
  await expect(hosts).toHaveValue("shop.example\n*.cdn.shop.example");
  await expect(save).toBeDisabled();
});

test("an agent's page lists the tabs its browser has open, closes one and stops the browser", async ({ page }) => {
  const browser = machineOn().start(
    "coach",
    [
      browserTab({ id: 1, label: "main", title: "Cửa hàng", host: "shop.example", idle_seconds: 17, conversation_id: "c1" }),
      browserTab({ id: 2, label: "gio", title: "Giỏ hàng", host: "pay.shop.example", idle_seconds: 200, conversation_id: null }),
    ],
    { idleSeconds: 17 },
  );
  await mockApi(page, { agents: [master, coach({ browser: "act" })], browser });
  await page.goto("/#/manage/crew/coach");

  const card = page.getByTestId("browser-card");
  const state = card.getByTestId("browser-state");
  const rows = card.getByRole("list", { name: t.card.tabs }).getByRole("listitem");
  await expect(state).toHaveText(t.card.running(2));
  await expect(card.getByTestId("browser-activity")).toHaveText("rảnh 17 giây");
  // Last used first, each with what it shows and whose it is.
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(0)).toContainText("main");
  await expect(rows.nth(0)).toContainText("Cửa hàng");
  await expect(rows.nth(0)).toContainText("shop.example");
  await expect(rows.nth(0)).toContainText("rảnh 17 giây");
  await expect(rows.nth(1)).toContainText("gio");
  await expect(rows.nth(1)).toContainText(t.card.scheduled);
  await expect(rows.nth(1)).toContainText("rảnh 3 phút");

  const closed = page.waitForRequest((r) => r.method() === "DELETE" && /\/api\/agents\/coach\/browser\/tabs\/2$/.test(r.url()));
  await card.getByRole("button", { name: t.card.closeTabNamed("gio") }).click();
  await closed;
  await expect(rows).toHaveCount(1);
  await expect(rows).toContainText("main");
  await expect(state).toHaveText(t.card.running(1));
  expect(browser.tabIds("coach")).toEqual([1]);

  const stop = card.getByRole("button", { name: t.card.stop });
  await expect(stop).toHaveAccessibleDescription(t.card.stopNote);
  const stopped = page.waitForRequest((r) => r.method() === "POST" && /\/api\/agents\/coach\/browser\/stop$/.test(r.url()));
  await stop.click();
  await stopped;
  await expect(state).toHaveText(t.card.stopped);
  await expect(rows).toHaveCount(0);
  await expect(stop).toHaveCount(0);
  expect(browser.running("coach")).toBe(false);
  // Nothing of it was a change to the agent's file.
  await expect(page.getByTestId("agent-editor").getByText(vi.editor.clean)).toBeVisible();
});

test("a browser call that waits in the chat is said in a line above its arguments", async ({ page }) => {
  const pay = { kind: "click", ref: "e12", name: "Thanh toán", tab: "main" };
  await mockApi(page, { agents: [master, coach({ browser: "act" })], conversations: [paused("c1", "Giỏ hàng", "browser_act", pay)], browser: machineOn() });
  await page.goto("/#/chat/c1");

  const bar = page.getByRole("alertdialog");
  const said = bar.getByTestId("approval-call");
  const raw = bar.locator(".approval-text > code");
  await expect(said).toHaveText("Bấm «Thanh toán»");
  await expect(raw).toHaveText("kind=click, ref=e12, name=Thanh toán, tab=main");
  expect(await top(said)).toBeLessThan(await top(raw));
  await expect(bar.getByRole("button", { name: vi.approve, exact: true })).toBeEnabled();
});

test("a download that waits in the chat is said as what it presses and the name its file is kept under", async ({ page }) => {
  const invoice = { ref: "e7", name: "Tải hoá đơn", save_as: "hoa-don-10.pdf", tab: "main" };
  await mockApi(page, { agents: [master, coach({ browser: "act" })], conversations: [paused("c1", "Hoá đơn", "browser_download", invoice)], browser: machineOn() });
  await page.goto("/#/chat/c1");

  const bar = page.getByRole("alertdialog");
  const said = bar.getByTestId("approval-call");
  const raw = bar.locator(".approval-text > code");
  await expect(said).toHaveText("Bấm «Tải hoá đơn» để tải tệp về, lưu thành hoa-don-10.pdf");
  await expect(raw).toHaveText("ref=e7, name=Tải hoá đơn, save_as=hoa-don-10.pdf, tab=main");
  expect(await top(said)).toBeLessThan(await top(raw));
  await expect(bar.getByRole("button", { name: vi.approve, exact: true })).toBeEnabled();
});

test("a download that waits in the list of requests is said the same way, with no name where the call gives none", async ({ page }) => {
  const invoice = { ref: "e7", name: "Tải hoá đơn" };
  await mockApi(page, {
    agents: [master, coach({ browser: "act" })],
    conversations: [paused("c2", "Hoá đơn", "browser_download", invoice)],
    runs: [waiting("c2")],
    browser: machineOn(),
  });
  await page.goto("/#/manage/approvals");

  const row = page.getByTestId("attention-row");
  const said = row.getByTestId("approval-call");
  await expect(said).toHaveText("Bấm «Tải hoá đơn» để tải tệp về");
  expect(await top(said)).toBeLessThan(await top(row.locator(".approval-text > code")));
  await expect(row.locator(".approval-text > code")).toHaveText("ref=e7, name=Tải hoá đơn");
});

test("a browser call that waits in the list of requests is said under the server's reason", async ({ page }) => {
  const cart = { url: "https://shop.example/cart?item=1", tab: "main" };
  await mockApi(page, {
    agents: [master, coach({ browser: "read" })],
    conversations: [paused("c2", "Mua", "browser_navigate", cart, REASON)],
    runs: [waiting("c2")],
    browser: machineOn(),
  });
  await page.goto("/#/manage/approvals");

  const row = page.getByTestId("attention-row");
  const said = row.getByTestId("approval-call");
  await expect(said).toHaveText("Mở trang shop.example");
  await expect(row.getByText(REASON)).toBeVisible();
  expect(await top(row.getByText(REASON))).toBeLessThan(await top(said));
  expect(await top(said)).toBeLessThan(await top(row.locator(".approval-text > code")));
  await expect(row.locator(".approval-text > code")).toHaveText("url=https://shop.example/cart?item=1, tab=main");
});

test("a screenshot's step shows the picture small, as a link to the whole of it, and nothing for a picture that is gone", async ({ page }) => {
  await mockApi(page, {
    agents: [master, coach({ browser: "read" })],
    runs: [run({ id: "shots", agent_id: "coach", steps: [shot("tc1", "don", SHOT), shot("tc2", "gio", GONE)] })],
    pictures: { [`coach/${SHOT}`]: [1280, 720] },
    browser: machineOn(),
  });
  // The picture that is not in the workspace is asked for, and the answer is that it is not.
  const refused = page.waitForResponse((r) => r.status() === 404 && r.url().endsWith(fileUrl(GONE)));
  await page.goto("/#/manage/activity/shots");
  await refused;

  const steps = page.getByTestId("run-step");
  const taken = steps.filter({ hasText: "tab=don" });
  const thumb = taken.getByTestId("screenshot-thumb");
  await expect(thumb).toHaveAttribute("href", fileUrl(SHOT));
  await expect(thumb).toHaveAttribute("target", "_blank");
  await expect(thumb).toHaveAttribute("rel", "noreferrer");
  const picture = thumb.getByRole("img", { name: t.screenshotAlt("don") });
  await expect(picture).toHaveAttribute("loading", "lazy");
  await expect.poll(() => picture.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(1280);
  // A picture of a whole screen is drawn small, in its own shape.
  const box = (await picture.boundingBox())!;
  expect(box.width).toBeLessThanOrEqual(242);
  expect(box.height).toBeLessThanOrEqual(162);
  expect(box.width / box.height).toBeCloseTo(1280 / 720, 1);
  // Under the step's own line, and the step still opens what it answered.
  expect(await top(taken.getByText("tab=don"))).toBeLessThan(box.y);
  await expect(taken.getByRole("button", { name: vi.showOutput })).toBeVisible();

  const gone = steps.filter({ hasText: "tab=gio" });
  await expect(gone).toContainText("browser_screenshot");
  await expect(gone.getByTestId("screenshot-thumb")).toHaveCount(0);
  await expect(gone.getByRole("img")).toHaveCount(0);
  await expect(page.getByTestId("screenshot-thumb")).toHaveCount(1);
});

test.describe("on a phone", () => {
  // A touch screen at the width people hold.
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  // What a page puts in a title or a host has nowhere to break at: no space, and no hyphen
  // either, which a line may end after. A label is as long as an agent may make one.
  const LONG_HOST = "d3b07384d113edec49eaa6238ad5ff00c1f169fbd61e9b5bb2f0a7c8.cdn.shop.example";
  const LONG_TABS = [
    browserTab({ id: 1, label: "thanhtoandonhang20261013", title: "HoaDonDienTuDH20261013KHTT0001KhachHangThanThietBanSaoChinhThuc.pdf", host: LONG_HOST, conversation_id: "c1", idle_seconds: 4 }),
    browserTab({ id: 2, label: "gio", title: "", host: "", conversation_id: null, idle_seconds: 3600, busy: true }),
  ];
  const LONG_HOSTS = ["shop.example", `*.${LONG_HOST}`];

  test("the browser setting and the card of what runs stay inside the page, with every control big enough for a finger", async ({ page }) => {
    const browser = machineOn().start("coach", LONG_TABS, { busy: true });
    await mockApi(page, { agents: [master, coach({ browser: "act", browser_hosts: LONG_HOSTS })], browser });
    await page.goto("/#/manage/crew/coach");
    const tools = page.getByTestId("section-tools");
    const mode = tools.getByRole("combobox", { name: t.mode });
    const hosts = tools.getByRole("textbox", { name: t.hosts });
    const card = page.getByTestId("browser-card");

    await expect(mode).toHaveValue("act");
    await expect(tools.getByText(t.modeHint.act)).toBeVisible();
    await expect(hosts).toHaveValue(LONG_HOSTS.join("\n"));
    await expect(card.getByTestId("browser-state")).toHaveText(t.card.running(2));
    await expect(card.getByRole("list", { name: t.card.tabs }).getByRole("listitem")).toHaveCount(2);
    await expect(card.getByRole("button", { name: t.card.stop })).toBeVisible();

    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
    expect(await spills(page, '[data-testid="section-tools"]')).toEqual([]);
    expect(await spills(page, '[data-testid="browser-card"]')).toEqual([]);
    expect(await smallTargets(page, '[data-testid="browser-card"]')).toEqual([]);
    // Safari zooms the page into any field under 16px when it takes focus.
    for (const field of [mode, hosts]) {
      expect(await field.evaluate((el) => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16);
      expect((await field.boundingBox())!.height).toBeGreaterThanOrEqual(40);
    }
  });

  test("the words for a machine that gives the agent no browser, and for a line that is no host, wrap inside the page", async ({ page }) => {
    await mockApi(page, { agents: [master, coach({ browser: "read", browser_hosts: LONG_HOSTS })], browser: new FakeBrowser() });
    await page.goto("/#/manage/crew/coach");
    const tools = page.getByTestId("section-tools");

    await expect(tools.getByTestId("browser-machine-warning")).toHaveText(t.machineOffForAgent);
    await expect(page.getByTestId("browser-state")).toHaveText(t.card.machineOff);
    const pasted = `https://${LONG_HOST}/giohang`;
    await tools.getByRole("textbox", { name: t.hosts }).fill(pasted);
    await expect(tools.getByText(t.hostInvalid(pasted))).toBeVisible();

    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
    expect(await spills(page, '[data-testid="section-tools"]')).toEqual([]);
    expect(await spills(page, '[data-testid="browser-card"]')).toEqual([]);
  });

  test("the machine's card, with the command that installs a browser, stays inside the page", async ({ page }) => {
    const browser = new FakeBrowser().start("coach", [browserTab()]).start("default", [browserTab()]);
    browser.machine = browserMachine({ enabled: true, installed: false, version: "", missing: "browser", install_command: "uv run playwright install chromium" });
    await mockApi(page, { agents: [master, coach({ browser: "act" })], browser });
    await page.goto("/#/manage/connections");

    const card = page.getByTestId("browser-machine");
    await expect(card.getByTestId("browser-missing").locator("code")).toHaveText("uv run playwright install chromium");
    await expect(card.getByTestId("browser-machine-running")).toHaveText("Đang chạy cho 2 agent: HLV sức khoẻ, Trợ lý");
    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
    expect(await spills(page, '[data-testid="browser-machine"]')).toEqual([]);
  });

  test("a waiting call's line, whatever a page named its element, stays inside the page", async ({ page }) => {
    // A field named by the address it shows, and a code typed into it: neither has a space.
    const typed = { kind: "type", ref: "e4", name: "nguyenvana.khachhangthanthiet.20261013@thanhtoan.shop.example", text: "TET26KHACHHANGTHANTHIETGIAMGIA50PHANTRAM20261013MUAHANGTRUCTUYEN", tab: "main" };
    await mockApi(page, {
      agents: [master, coach({ browser: "act" })],
      conversations: [paused("c2", "Mua", "browser_act", typed, REASON)],
      runs: [waiting("c2")],
      browser: machineOn(),
    });
    await page.goto("/#/manage/approvals");

    const row = page.getByTestId("attention-row");
    await expect(row.getByTestId("approval-call")).toContainText("Gõ «TET26KHACH");
    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
    expect(await spills(page, '[data-testid="attention-row"]')).toEqual([]);

    await page.goto("/#/chat/c2");
    const bar = page.getByRole("alertdialog");
    await expect(bar.getByTestId("approval-call")).toContainText("Gõ «TET26KHACH");
    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
    expect(await spills(page, ".approval-bar")).toEqual([]);
  });

  test("a screenshot's picture is no wider than its step, and a sliver of a whole page is still big enough for a finger", async ({ page }) => {
    await mockApi(page, {
      agents: [master, coach({ browser: "read" })],
      runs: [run({ id: "shots", agent_id: "coach", steps: [shot("tc1", "don", SHOT), shot("tc2", "ca_trang", WHOLE_PAGE)] })],
      // A screen, and a page sixteen times taller than it is wide.
      pictures: { [`coach/${SHOT}`]: [1280, 720], [`coach/${WHOLE_PAGE}`]: [320, 5120] },
      browser: machineOn(),
    });
    await page.goto("/#/manage/activity/shots");

    const steps = page.getByTestId("run-step");
    const ofScreen = steps.filter({ hasText: "tab=don" }).getByRole("img");
    const ofPage = steps.filter({ hasText: "tab=ca_trang" }).getByRole("img");
    await expect.poll(() => ofScreen.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(1280);
    await expect.poll(() => ofPage.evaluate((img: HTMLImageElement) => img.naturalHeight)).toBe(5120);

    const [wide, tall] = [(await ofScreen.boundingBox())!, (await ofPage.boundingBox())!];
    expect(wide.x + wide.width).toBeLessThanOrEqual(390);
    expect(wide.width / wide.height).toBeCloseTo(1280 / 720, 1);
    expect(tall.height).toBeLessThanOrEqual(162);
    expect(tall.width).toBeLessThan(40);
    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
    expect(await smallTargets(page, '[data-testid="run-card"]')).toEqual([]);
  });
});
