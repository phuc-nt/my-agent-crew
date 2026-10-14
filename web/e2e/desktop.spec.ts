// An agent's desktop as a person meets it on the page: the machine's helper and its two
// permissions, on the connections page; the agent's own setting and a trial picture, on its
// page; a waiting computer_act call said in a line over the picture it was chosen on; and the
// picture a screenshot saved, small on its step.
import { expect, type Locator, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { DESKTOP_SAID, FakeDesktop, desktopReady } from "../src/test/fake-desktop";
import { type Conversation, coachAgent, defaultAgent, mockApi, run } from "./mock-api";
import { smallTargets } from "./small-targets";
import { spills } from "./spills";

const t = vi.desktop;
const master = { ...defaultAgent, name: "Trợ lý", delegates: ["coach"] };
const coach = (rest: object = {}) => ({ ...coachAgent, declared: { delegates: [], schedules: [], tools: [] }, computer: "off", computer_apps: [], ...rest });
/** A machine whose helper answered, with what a test says of it. */
const helper = (machine: Parameters<typeof desktopReady>[0] = {}) => Object.assign(new FakeDesktop(), { machine: desktopReady(machine) });

const F = "00000000000000a1-1456x910-1";
const SHOT_AT = "2026-10-14T02:05:00Z";
const fileUrl = (path: string) => `/api/agents/coach/files?path=${encodeURIComponent(path)}`;
const saved = (path: string, frame = F) =>
  `Đã chụp màn hình và lưu vào ${path}. frame_id: ${frame} (1456×910; toạ độ của computer_act tính theo điểm ảnh của ảnh này).\nỨng dụng phía trước: Notes`;
const unchanged = (path: string) =>
  `Màn hình không đổi từ lần chụp trước. frame_id: ${F} (1456×910); ảnh đã lưu ở ${path} vẫn đúng. Muốn hỏi về ảnh thì gọi lại kèm \`question\`.`;

const top = async (of: Locator) => (await of.boundingBox())!.y;
const loaded = (img: Locator) => expect.poll(() => img.evaluate((el: HTMLImageElement) => el.naturalWidth));
/** Where a mark's centre is on its picture, as fractions of the picture's width and height. */
async function placed(mark: Locator, picture: Locator): Promise<[number, number]> {
  const [m, p] = [(await mark.boundingBox())!, (await picture.boundingBox())!];
  return [(m.x + m.width / 2 - p.x) / p.width, (m.y + m.height / 2 - p.y) / p.height];
}
/** The GETs of the connections page, counted as the page sends them. */
function connectionReads(page: Page): () => number {
  let reads = 0;
  page.on("request", (r) => {
    if (r.method() === "GET" && /\/api\/connections$/.test(r.url())) reads += 1;
  });
  return () => reads;
}

/** A conversation of the coach's whose screenshot saved `shotPath` (or took none), paused on
 *  one computer_act call. */
function paused(id: string, args: Record<string, unknown>, shotPath: string | null, reason?: string): Conversation {
  const message = (seq: number, rest: object) => ({
    id: `m${seq}`, seq, role: "assistant", content: "", tool_calls: [], tool_call_id: null, name: null, provider: null, model: null, cost_usd: null, created_at: SHOT_AT, ...rest,
  });
  const shot = shotPath
    ? [
        message(1, { tool_calls: [{ id: "s1", name: "computer_screenshot", arguments: {} }] }),
        message(2, { role: "tool", content: saved(shotPath), tool_call_id: "s1", name: "computer_screenshot" }),
      ]
    : [];
  return {
    id, agent_id: "coach", channel: "", title: "Ghi chú", summary: "", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "awaiting_approval", over_budget: false, parent_call_id: "",
    messages: [...shot, message(3, { tool_calls: [{ id: "tc", name: "computer_act", arguments: args }] })],
    pending_approval: {
      id: "ap", conversation_id: id, message_id: "m3", tool_call_id: "tc", tool_name: "computer_act", arguments: args, status: "pending", created_at: "",
      expires_at: new Date(Date.now() + 5 * 60_000).toISOString(), resolved_at: null, kind: "tool", ...(reason !== undefined ? { reason } : {}),
    },
  };
}
const waiting = (conversationId: string) =>
  run({ id: `wait-${conversationId}`, agent_id: "coach", conversation_id: conversationId, status: "awaiting_approval", finished_at: null, summary: "" });

test("the connections page says the machine has no helper, and nothing there sends a thing", async ({ page }) => {
  const desktop = new FakeDesktop();
  await mockApi(page, { agents: [master, coach()], desktop });
  await page.goto("/#/manage/connections");

  const card = page.getByTestId("desktop-machine");
  await expect(card.getByRole("heading", { name: t.title })).toBeVisible();
  await expect(card.getByTestId("desktop-machine-state")).toHaveText(t.machine.absent);
  await expect(card.locator("button, input, select, textarea, a")).toHaveCount(0);
  expect(desktop.presses).toBe(0);
});

test("the connections page asks macOS for the permissions on a press only, then reads the helper again", async ({ page }) => {
  const desktop = helper({ accessibility: false });
  desktop.granted = { accessibility: true };
  const { posted } = await mockApi(page, { agents: [master, coach()], desktop });
  const reads = connectionReads(page);
  await page.goto("/#/manage/connections");

  const card = page.getByTestId("desktop-machine");
  const state = card.getByTestId("desktop-machine-state");
  await expect(state).toContainText(t.machine.present);
  await expect(state).toContainText(t.machine.version("0.1.0"));
  await expect(card.getByTestId("desktop-permission-screen_recording")).toContainText(t.machine.granted);
  await expect(card.getByTestId("desktop-permission-accessibility")).toContainText(t.machine.missing);
  const ask = card.getByRole("button", { name: t.machine.ask });
  await expect(ask).toBeEnabled();
  await expect(card.getByText(t.machine.askHint)).toBeVisible();
  // Read, and nothing asked of macOS by the reading.
  const readsBefore = reads();
  expect(desktop.presses).toBe(0);
  expect(posted.filter((p) => p.path === "/desktop/permissions")).toHaveLength(0);

  const asked = page.waitForRequest((r) => r.method() === "POST" && /\/api\/desktop\/permissions$/.test(r.url()));
  await ask.click();
  await asked;
  await expect(card.getByTestId("desktop-permission-accessibility")).toContainText(t.machine.granted);
  await expect(ask).toHaveCount(0);
  await expect(card.getByTestId("desktop-still-missing")).toHaveCount(0);
  expect(reads()).toBe(readsBefore + 1);
  expect(desktop.presses).toBe(1);
});

test("a permission still missing after a press is the owner's to grant, and a locked screen's refusal is shown as it is", async ({ page }) => {
  const desktop = helper({ screen_recording: false });
  await mockApi(page, { agents: [master, coach()], desktop });
  await page.goto("/#/manage/connections");
  const card = page.getByTestId("desktop-machine");
  const ask = card.getByRole("button", { name: t.machine.ask });

  await ask.click();
  await expect(card.getByTestId("desktop-still-missing")).toHaveText(t.machine.stillMissing(t.permission.screen_recording));
  await expect(card.getByTestId("desktop-permission-screen_recording")).toContainText(t.machine.missing);
  await expect(ask).toBeEnabled();
  expect(desktop.presses).toBe(1);

  desktop.machine = { ...desktop.machine, locked: true };
  await ask.click();
  await expect(card.getByTestId("desktop-ask-error")).toHaveText(DESKTOP_SAID.locked);
  // Read again all the same: the page now says why.
  await expect(card.getByTestId("desktop-machine-state")).toContainText(t.machine.locked);
  expect(desktop.presses).toBe(2);
});

test("an agent's desktop is turned on with its applications, saved as the word and a list, kept after a reload, and emptied as an empty list", async ({ page }) => {
  await mockApi(page, { agents: [master, coach()], desktop: helper() });
  await page.goto("/#/manage/crew/coach");
  const editor = page.getByTestId("agent-editor");
  const tools = editor.getByTestId("section-tools");
  const mode = tools.getByRole("combobox", { name: t.editor.mode });
  const apps = tools.getByRole("textbox", { name: t.editor.apps });
  const save = editor.getByRole("button", { name: vi.editor.save, exact: true });
  const card = page.getByTestId("desktop-card");
  const patched = () => page.waitForRequest((r) => r.method() === "PATCH" && /\/api\/agents\/coach$/.test(r.url()));

  await expect(mode).toHaveValue("off");
  await expect(mode).toHaveAccessibleDescription(t.editor.modeHint.off);
  await expect(apps).toHaveCount(0);
  await expect(tools.getByTestId("desktop-helper-note")).toHaveText(t.editor.helperNote);
  await expect(tools.getByText(t.outsideList)).toBeVisible();
  await expect(card.getByTestId("desktop-mode")).toHaveText(t.card.mode.off);
  await expect(card.getByRole("button", { name: t.card.tryShot })).toHaveCount(0);
  await expect(save).toBeDisabled();

  await mode.selectOption("on");
  await expect(mode).toHaveAccessibleDescription(t.editor.modeHint.on);
  await expect(apps).toHaveAccessibleDescription(t.editor.appsHint);
  await apps.fill("Notes\n\n  com.apple.Safari  \nNotes\n");
  let patch = patched();
  await save.click();
  expect((await patch).postDataJSON()).toEqual({ profile: { computer: "on", computer_apps: ["Notes", "com.apple.Safari"] } });
  await expect(editor.getByText(vi.editor.clean)).toBeVisible();
  // The card reads the agent again as it now is.
  await expect(card.getByTestId("desktop-mode")).toHaveText(t.card.mode.on);
  await expect(card.getByTestId("desktop-apps-line")).toHaveText(t.card.apps("Notes, com.apple.Safari"));
  await expect(card.getByRole("button", { name: t.card.tryShot })).toBeEnabled();

  await page.reload();
  await expect(mode).toHaveValue("on");
  await expect(apps).toHaveValue("Notes\ncom.apple.Safari");
  await expect(save).toBeDisabled();

  await apps.fill("");
  patch = patched();
  await save.click();
  expect((await patch).postDataJSON()).toEqual({ profile: { computer_apps: [] } });
  await expect(card.getByTestId("desktop-apps-line")).toHaveText(t.card.lookOnly);
  await page.reload();
  await expect(apps).toHaveValue("");
  await expect(card.getByTestId("desktop-apps-line")).toHaveText(t.card.lookOnly);
});

test("a refused application list is said beside the box, which keeps what was typed", async ({ page }) => {
  await mockApi(page, { agents: [master, coach({ computer: "on", computer_apps: ["Notes"] })], desktop: helper() });
  await page.goto("/#/manage/crew/coach");
  const editor = page.getByTestId("agent-editor");
  const apps = editor.getByTestId("section-tools").getByRole("textbox", { name: t.editor.apps });
  const typed = `Notes\n${"x".repeat(201)}`;

  await apps.fill(typed);
  const refused = page.waitForResponse((r) => r.status() === 422 && /\/api\/agents\/coach$/.test(r.url()));
  await editor.getByRole("button", { name: vi.editor.save, exact: true }).click();
  await refused;
  const said = "agent coach: computer_apps must be a list of application names or bundle ids, such as Notes or com.apple.Notes";
  await expect(apps).toHaveAccessibleDescription(`${t.editor.appsHint} ${said}`);
  await expect(apps).toHaveAttribute("aria-invalid", "true");
  // Beside the box it is about, the one that takes the next line.
  const error = editor.locator(".field-error", { hasText: said });
  expect(await top(apps)).toBeLessThan(await top(error));
  expect(await top(error)).toBeLessThan(await top(editor.getByTestId("desktop-helper-note")));
  await expect(apps).toHaveValue(typed);
  await expect(editor.getByTestId("desktop-mode-error")).toHaveCount(0);
});

test("an agent's page takes a trial picture and shows it, and says as it is why it cannot take one", async ({ page }) => {
  const desktop = helper();
  const path = "records/kept/desktop/0000000000000001-1456x910-1.png";
  const { posted } = await mockApi(page, {
    agents: [master, coach({ computer: "on", computer_apps: ["Notes"], write_paths: ["records/kept"] })],
    desktop,
    pictures: { [`coach/${path}`]: [1456, 910] },
  });
  let answer = () => {};
  desktop.holdShot = new Promise<void>((resolve) => (answer = resolve));
  await page.goto("/#/manage/crew/coach");

  const card = page.getByTestId("desktop-card");
  await expect(card.getByTestId("desktop-mode")).toHaveText(t.card.mode.on);
  await expect(card.getByTestId("desktop-apps-line")).toHaveText(t.card.apps("Notes"));
  await expect(card.getByTestId("desktop-machine-lines")).toHaveText(t.card.ready);
  const tryIt = card.getByTestId("desktop-try");
  await expect(tryIt).toHaveText(t.card.tryShot);
  await expect(tryIt).toHaveAccessibleDescription(t.card.tryHint);

  await tryIt.click();
  // One at a time: the button waits while the helper does.
  await expect(tryIt).toHaveText(t.card.shooting);
  await expect(tryIt).toBeDisabled();
  answer();
  const shot = card.getByTestId("desktop-shot");
  await expect(shot).toHaveAttribute("href", fileUrl(path));
  const picture = shot.getByRole("img", { name: t.card.shotAlt(1456, 910) });
  await loaded(picture).toBe(1456);
  await expect(tryIt).toBeEnabled();
  expect(desktop.shots.map((s) => s.path)).toEqual([path]);
  // Nothing of it is a change to the agent's file.
  await expect(page.getByTestId("agent-editor").getByText(vi.editor.clean)).toBeVisible();

  desktop.holdShot = null;
  desktop.machine = { ...desktop.machine, locked: true };
  await tryIt.click();
  await expect(card.getByTestId("desktop-refused")).toHaveText(DESKTOP_SAID.locked);
  await expect(shot).toHaveCount(0);
  await expect(card.getByTestId("desktop-machine-lines")).toHaveText(t.card.locked);
  expect(posted.filter((p) => p.path === "/agents/coach/desktop/screenshot")).toHaveLength(2);
  expect(desktop.presses).toBe(0);
});

test("a desktop action that waits in the chat is said in a line, over the picture it was chosen on with its point marked, over its arguments", async ({ page }) => {
  const path = `desktop/${F}.png`;
  const click = { kind: "click", app: "Notes", frame_id: F, x: 364, y: 682.5 };
  await mockApi(page, {
    agents: [master, coach({ computer: "on", computer_apps: ["Notes"] })],
    conversations: [paused("c1", click, path, "")],
    pictures: { [`coach/${path}`]: [1456, 910] },
    desktop: helper(),
  });
  await page.goto("/#/chat/c1");

  const bar = page.getByRole("alertdialog");
  const said = bar.getByTestId("approval-call");
  const raw = bar.locator(".approval-text > code");
  await expect(said).toHaveText("Bấm tại điểm (364, 682.5) trong Notes");
  await expect(bar.locator(".approval-reason")).toHaveCount(0);
  await expect(raw).toHaveText(`kind=click, app=Notes, frame_id=${F}, x=364, y=682.5`);

  const frame = bar.getByTestId("desktop-frame");
  const picture = frame.getByRole("img", { name: t.frame.alt(1456, 910) });
  await expect(picture).toHaveAttribute("src", fileUrl(path));
  await loaded(picture).toBe(1456);
  await expect(frame.getByRole("link")).toHaveAttribute("href", fileUrl(path));
  // Drawn small and in its own shape, and the mark sits on the point the call names.
  const box = (await picture.boundingBox())!;
  expect(box.width).toBeLessThanOrEqual(321);
  expect(box.width / box.height).toBeCloseTo(1456 / 910, 1);
  expect((await frame.getByRole("link").boundingBox())!).toEqual(box);
  const [x, y] = await placed(frame.getByTestId("desktop-frame-point"), picture);
  expect(x).toBeCloseTo(0.25, 2);
  expect(y).toBeCloseTo(0.75, 2);
  // When the agent saw it, in the owner's time.
  const when = frame.getByTestId("desktop-frame-time");
  await expect(when).toHaveText(/^Ảnh chụp lúc 09:05 14\D10; /);
  expect(await top(said)).toBeLessThan(await top(picture));
  expect(await top(picture)).toBeLessThan(await top(raw));
  await expect(bar.getByRole("button", { name: vi.approve, exact: true })).toBeEnabled();
});

test("a drag that waits in the list of requests marks both ends on the agent's folder picture, under the server's reason", async ({ page }) => {
  const reason = "kéo thả luôn hỏi trước, kể cả khi hội thoại tự chủ";
  // A screen turned on its side: a shape no default could stand in for.
  const tall = "00000000000000b2-1080x1920-2";
  const drag = { kind: "drag", app: "Notes", frame_id: tall, x: 0, y: 960, to_x: 1080, to_y: 1920 };
  await mockApi(page, {
    agents: [master, coach({ computer: "on", computer_apps: ["Notes"], write_paths: ["records/kept"] })],
    conversations: [paused("c2", drag, null, reason)],
    runs: [waiting("c2")],
    pictures: { [`coach/records/kept/desktop/${tall}.png`]: [1080, 1920] },
    desktop: helper(),
  });
  await page.goto("/#/manage/approvals");

  const row = page.getByTestId("attention-row");
  const said = row.getByTestId("approval-call");
  await expect(said).toHaveText("Kéo từ điểm (0, 960) tới điểm (1080, 1920) trong Notes");
  expect(await top(row.getByText(reason))).toBeLessThan(await top(said));
  const picture = row.getByTestId("desktop-frame").getByRole("img");
  await loaded(picture).toBe(1080);
  // Drawn in the frame's own shape, no taller than a card can hold, and the box the marks are
  // placed in is the picture's.
  const box = (await picture.boundingBox())!;
  expect(box.width / box.height).toBeCloseTo(1080 / 1920, 1);
  expect(box.height).toBeLessThanOrEqual(225);
  expect((await row.getByTestId("desktop-frame").getByRole("link").boundingBox())!).toEqual(box);
  // A picture no screenshot of the conversation named: no time to tell.
  await expect(row.getByTestId("desktop-frame-time")).toHaveCount(0);
  const points = row.getByTestId("desktop-frame-point");
  await expect(points).toHaveCount(2);
  const [from, to] = [await placed(points.nth(0), picture), await placed(points.nth(1), picture)];
  expect(from[0]).toBeCloseTo(0, 2);
  expect(from[1]).toBeCloseTo(0.5, 2);
  expect(to[0]).toBeCloseTo(1, 2);
  expect(to[1]).toBeCloseTo(1, 2);
  await expect(points.nth(1)).toHaveAttribute("title", t.frame.dropPoint);
});

test("a desktop action whose picture is not kept any more waits with its line and its arguments, and no picture", async ({ page }) => {
  const click = { kind: "click", app: "Notes", frame_id: F, ref: "e12", name: "Lưu" };
  const gone = page.waitForResponse((r) => r.status() === 404 && r.url().endsWith(fileUrl(`desktop/${F}.png`)));
  await mockApi(page, { agents: [master, coach({ computer: "on", computer_apps: ["Notes"] })], conversations: [paused("c1", click, `desktop/${F}.png`)], desktop: helper() });
  await page.goto("/#/chat/c1");
  await gone;

  const bar = page.getByRole("alertdialog");
  await expect(bar.getByTestId("approval-call")).toHaveText("Bấm «Lưu» (e12) trong Notes");
  await expect(bar.getByTestId("desktop-frame")).toHaveCount(0);
  await expect(bar.locator(".approval-text > code")).toContainText(`frame_id=${F}`);
});

test("a screenshot's step shows the picture it saved, and an unchanged screen's step the same picture", async ({ page }) => {
  const DEEP = "records/kept/for/the/owner/by/this/agent";
  const path = `${DEEP}/desktop/${F}.png`;
  /** What a run's step keeps of an answer: one line, cut at 160 characters. */
  const preview = (text: string) => {
    const flat = text.split(/\s+/).filter(Boolean).join(" ");
    return flat.length <= 160 ? flat : `${flat.slice(0, 160)}…`;
  };
  const step = (id: string, output: string) => ({ kind: "tool", name: "computer_screenshot", tool_call_id: id, arguments: {}, ok: true, output, duration_ms: 900 });
  await mockApi(page, {
    agents: [master, coach({ computer: "on", computer_apps: [], write_paths: [DEEP] })],
    runs: [run({ id: "shots", agent_id: "coach", steps: [step("s1", preview(saved(path))), step("s2", preview(unchanged(path)))] })],
    pictures: { [`coach/${path}`]: [1456, 910] },
    desktop: helper(),
  });
  await page.goto("/#/manage/activity/shots");

  const thumbs = page.getByTestId("screenshot-thumb");
  await expect(thumbs).toHaveCount(2);
  for (const at of [0, 1]) {
    await expect(thumbs.nth(at)).toHaveAttribute("href", fileUrl(path));
    await expect(thumbs.nth(at)).toHaveAttribute("target", "_blank");
    await loaded(thumbs.nth(at).getByRole("img", { name: t.screenshotAlt(1456, 910) })).toBe(1456);
  }
});

test.describe("on a phone", () => {
  // A touch screen at the width people hold.
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  // A bundle id comes with no space or hyphen to break at.
  const LONG_APP = "com.example.ungdungghichepdaikhongcochongatdong20261014banquyenchinhthuc";
  const pageWidth = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth);

  test("the desktop setting, the agent's card with its picture, and the machine's row stay inside the page, with every control big enough for a finger", async ({ page }) => {
    const desktop = helper({ accessibility: false });
    const path = "desktop/0000000000000001-1456x910-1.png";
    await mockApi(page, {
      agents: [master, coach({ computer: "on", computer_apps: [LONG_APP, "Notes"] })],
      desktop,
      pictures: { [`coach/${path}`]: [1456, 910] },
    });
    await page.goto("/#/manage/crew/coach");
    const tools = page.getByTestId("section-tools");
    const mode = tools.getByRole("combobox", { name: t.editor.mode });
    const apps = tools.getByRole("textbox", { name: t.editor.apps });
    const card = page.getByTestId("desktop-card");

    await expect(apps).toHaveValue(`${LONG_APP}\nNotes`);
    await expect(card.getByTestId("desktop-apps-line")).toHaveText(t.card.apps(`${LONG_APP}, Notes`));
    await card.getByTestId("desktop-try").click();
    await loaded(card.getByTestId("desktop-shot").getByRole("img")).toBe(1456);

    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
    expect(await spills(page, '[data-testid="section-tools"]')).toEqual([]);
    expect(await spills(page, '[data-testid="desktop-card"]')).toEqual([]);
    expect(await smallTargets(page, '[data-testid="desktop-card"]')).toEqual([]);
    // Safari zooms the page into any field under 16px when it takes focus.
    for (const field of [mode, apps]) {
      expect(await field.evaluate((el) => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16);
      expect((await field.boundingBox())!.height).toBeGreaterThanOrEqual(40);
    }

    await page.goto("/#/manage/connections");
    await expect(page.getByTestId("desktop-machine").getByRole("button", { name: t.machine.ask })).toBeVisible();
    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
    expect(await spills(page, '[data-testid="desktop-machine"]')).toEqual([]);
    expect(await smallTargets(page, '[data-testid="desktop-machine"]')).toEqual([]);
    expect(desktop.presses).toBe(0);
  });

  test("a waiting action's picture and its mark stay inside the page", async ({ page }) => {
    // At the picture's far corner, in an application named by a long bundle id.
    const click = { kind: "click", app: LONG_APP, frame_id: F, x: 1456, y: 910 };
    await mockApi(page, {
      agents: [master, coach({ computer: "on", computer_apps: [LONG_APP] })],
      conversations: [paused("c2", click, `desktop/${F}.png`)],
      runs: [waiting("c2")],
      pictures: { [`coach/desktop/${F}.png`]: [1456, 910] },
      desktop: helper(),
    });
    await page.goto("/#/manage/approvals");

    const row = page.getByTestId("attention-row");
    const picture = row.getByTestId("desktop-frame").getByRole("img");
    await loaded(picture).toBe(1456);
    const [x, y] = await placed(row.getByTestId("desktop-frame-point"), picture);
    expect([x, y].map((v) => Math.round(v * 100) / 100)).toEqual([1, 1]);
    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
    // The ring on the picture's corner reaches past it and is cut at its edge: every box around
    // the picture holds. The picture's own box is left out of that count only because it
    // clips, so its scroll width counts what nobody sees.
    const frameBox = row.locator(".desktop-frame-picture");
    const clipped = (await spills(page, '[data-testid="attention-row"]')).filter((s) => !s.startsWith("a.desktop-frame-picture "));
    expect(clipped).toEqual([]);
    expect(await frameBox.evaluate((el) => getComputedStyle(el).overflow)).toBe("clip");
    const [rowBox, pictureBox] = [(await row.boundingBox())!, (await frameBox.boundingBox())!];
    expect(pictureBox.x + pictureBox.width).toBeLessThanOrEqual(rowBox.x + rowBox.width);
    expect(await smallTargets(page, '[data-testid="desktop-frame"]')).toEqual([]);
  });
});
