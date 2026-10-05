import { expect, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeCanvas } from "../src/test/fake-canvas";
import { type Conversation, coachAgent, defaultAgent, mockApi } from "./mock-api";

const { card } = vi.canvas;
const PLAN = "00ff00ff00ff";
const SHOP = "ba9876543210";
const LOST = "0000000000ff";
const REPORT = "Báo cáo tuần";
const ANNEX = "Phụ lục";
// A title with nowhere to break, wider than a phone.
const LONG_TITLE = `Biên bản ${"kéodàikhôngngắt".repeat(8)}`;
const REPLY = "Việc đã xong.";
const TASK = { agent: "coach", task: "viết báo cáo tuần" };

const SCREENS = [
  ["a wide screen", { viewport: { width: 1440, height: 900 } }],
  ["a phone", { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true }],
] as const;

const line = (id: string, version: number, title: string) => `[artifact ${id} v${version}] ${title}`;

/** What the handed-off task returns, as the server writes it: the canvases it wrote above a blank line. */
const result = (canvases: string[], reply = "Đã viết báo cáo.") =>
  ["conversation=c-child status=done spent=$0.0100 steps=3", "outcome=done", ...canvases, "", reply].join("\n");

const WROTE = result([line(PLAN, 2, REPORT), line(SHOP, 1, ANNEX)]);

/** A turn in which the agent hands the task off and says how it went, as the server streams it. */
function turn(output: string) {
  return [
    {
      type: "assistant_message", message_id: "a1", content: "", provider: null, model: null, cost_usd: null,
      tool_calls: [{ id: "d1", name: "delegate", arguments: TASK }],
    },
    { type: "tool_call", tool_call_id: "d1", name: "delegate", arguments: TASK },
    { type: "tool_result", tool_call_id: "d1", name: "delegate", ok: true, output },
    { type: "assistant_message", message_id: "a2", content: REPLY, tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
    { type: "done", spent_usd: 0.01, unknown_cost_calls: 0 },
  ];
}

/** A conversation with nothing said in it yet. */
function quiet(): Conversation {
  return {
    id: "c1", agent_id: "default", channel: "", title: "Báo cáo", summary: "", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "idle", over_budget: false, parent_call_id: "", pending_approval: null, messages: [],
  };
}

/** The first message is sent, and the agent answers it by handing the task to another, whose result is `output`.
 *  The canvases that agent wrote are its own: the conversation asking is not given them. */
async function handOff(page: Page, output: string, title = REPORT) {
  const fake = new FakeCanvas();
  fake.add({ id: PLAN, title, agent_id: "coach", content: "Tuần này\n\nBa việc xong", version: 2 });
  fake.add({ id: SHOP, title: ANNEX, agent_id: "coach", content: "Số liệu" });
  await mockApi(page, {
    agents: [{ ...defaultAgent, delegates: ["coach"] }, coachAgent],
    conversations: [quiet()],
    canvas: fake,
    turns: [turn(output)],
  });
  await page.goto("/#/chat/c1");
  const box = page.getByRole("textbox", { name: vi.composerPlaceholder });
  await box.fill("giao việc viết báo cáo");
  await box.press("Enter");
  await expect(page.getByTestId("message-assistant")).toContainText(REPLY);
  return { box };
}

const chips = (page: Page) => page.getByTestId("delegate-card").getByTestId("delegate-canvas");
const openButton = (page: Page, title: string) => page.getByTestId("delegate-card").getByRole("button", { name: card.openLabel(title) });
const panelTitle = (page: Page, name: string) => page.getByRole("heading", { level: 2, name });

/** What a person would have to scroll sideways to read: the page, the thread, or a part of the card. */
function overflowing(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    [document.documentElement, ...document.querySelectorAll<HTMLElement>(".thread, .delegate-card, .delegate-canvases, .delegate-canvas")]
      .filter((el) => el.scrollWidth > el.clientWidth)
      .map((el) => `${el.tagName.toLowerCase()}.${el.className} ${el.scrollWidth}>${el.clientWidth}`),
  );
}

/** How the chips sit in their card: the first from edge to edge of it with its button at its right end, the
 *  rest under it, and what is said beside each name kept whole on one line. */
function placed(page: Page) {
  return page.evaluate(() => {
    const all = (selector: string) => [...document.querySelectorAll<HTMLElement>(selector)];
    const box = (selector: string) => all(selector)[0].getBoundingClientRect();
    const lines = (el: HTMLElement) => Math.round(el.getBoundingClientRect().height / Number.parseFloat(getComputedStyle(el).lineHeight));
    const [cardBox, chip, title, icon] = [".delegate-card", ".delegate-canvas", ".delegate-canvas .canvas-chip-title", ".delegate-canvas .tool-icon"].map(box);
    const button = all(".delegate-canvas button")[0]?.getBoundingClientRect();
    const tops = all(".delegate-canvas").map((el) => el.getBoundingClientRect());
    return {
      inside: chip.left >= cardBox.left && chip.right <= cardBox.right,
      buttonAtEnd: button !== undefined && button.left >= title.right && Math.abs(button.right - chip.right) < 1,
      underCost: chip.top >= box(".delegate-result").bottom,
      stacked: tops.every((at, i) => i === 0 || (at.top >= tops[i - 1].bottom && at.left === tops[0].left)),
      iconWhole: icon.width > 0 && Math.abs(icon.width - icon.height) < 0.5,
      titleLines: lines(all(".delegate-canvas .canvas-chip-title")[0]),
      besideLines: all(".delegate-canvas > .muted").map(lines),
    };
  });
}

for (const [name, screen] of SCREENS) {
  test.describe(`the card of a handed-off task on ${name}`, () => {
    test.use(screen);

    test("names the canvases the other agent wrote, each at its version with a way to open it, under how the task went", async ({ page }) => {
      await handOff(page, WROTE);

      await expect(chips(page)).toHaveText([`${REPORT}v2${card.open}`, `${ANNEX}v1${card.open}`]);
      await expect(page.getByRole("list", { name: vi.canvas.delegateCanvases })).toBeVisible();
      await expect(openButton(page, REPORT)).toBeVisible();
      await expect(openButton(page, ANNEX)).toBeVisible();
      expect(await placed(page)).toEqual({ inside: true, buttonAtEnd: true, underCost: true, stacked: true, iconWhole: true, titleLines: 1, besideLines: [1, 1] });
      expect(await overflowing(page)).toEqual([]);
    });

    test("names none for a task that wrote none, and opens nothing", async ({ page }) => {
      await handOff(page, result([]));

      await expect(page.getByTestId("delegate-card")).toBeVisible();
      await expect(chips(page)).toHaveCount(0);
      await expect(page.getByRole("list", { name: vi.canvas.delegateCanvases })).toHaveCount(0);
      await expect(panelTitle(page, REPORT)).toHaveCount(0);
    });

    test("names none for a reply that only opens with a line like the server's", async ({ page }) => {
      await handOff(page, result([], `${line(PLAN, 2, REPORT)}\n\nXem canvas trên.`));

      await expect(page.getByTestId("delegate-card")).toBeVisible();
      await expect(chips(page)).toHaveCount(0);
      await expect(panelTitle(page, REPORT)).toHaveCount(0);
    });

    test("says a canvas the server no longer has is deleted, and offers nothing to open it with", async ({ page }) => {
      await handOff(page, result([line(SHOP, 1, ANNEX), line(LOST, 3, "Bản đã xoá")]));

      const gone = chips(page).nth(1);
      await expect(gone).toContainText("Bản đã xoá");
      await expect(gone).toContainText(vi.canvas.gone);
      await expect(gone.getByRole("button")).toHaveCount(0);
      await expect(openButton(page, ANNEX)).toBeVisible();
      expect(await overflowing(page)).toEqual([]);
    });

    test("keeps a name too long for the screen inside the card, with its button still on it and what is beside it whole", async ({ page }) => {
      await handOff(page, result([line(PLAN, 2, LONG_TITLE), line(LOST, 3, LONG_TITLE)]), LONG_TITLE);

      await expect(chips(page)).toHaveCount(2);
      await expect(openButton(page, LONG_TITLE)).toBeVisible();
      await expect(chips(page).nth(1)).toContainText(vi.canvas.gone);
      const { titleLines, ...at } = await placed(page);
      // The name is what gives way: it wraps, and the version, the button and the word that it is deleted do not.
      expect(titleLines).toBeGreaterThan(1);
      expect(at).toEqual({ inside: true, buttonAtEnd: true, underCost: true, stacked: true, iconWhole: true, besideLines: [1, 1] });
      expect(await overflowing(page)).toEqual([]);
    });
  });
}

test.describe("on a wide screen", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the first canvas a handed-off task wrote opens beside the thread while the keyboard stays in the box", async ({ page }) => {
    const messages: unknown[] = [];
    page.on("request", (request) => {
      const { pathname } = new URL(request.url());
      if (request.method() === "POST" && pathname === "/api/conversations/c1/messages") messages.push(request.postDataJSON());
    });
    const { box } = await handOff(page, WROTE);

    await expect(panelTitle(page, REPORT)).toBeVisible();
    await expect(panelTitle(page, ANNEX)).toHaveCount(0);
    await expect(box).toBeFocused();
    await page.keyboard.type("rút gọn");
    await expect(box).toHaveValue("rút gọn");

    // The canvas on show is the one the next message is about.
    await box.press("Enter");
    await expect.poll(() => messages.length).toBe(2);
    expect(messages[1]).toEqual({ text: "rút gọn", canvas: { artifact_id: PLAN, selection: null } });
  });

  test("a chip's Open shows that canvas in place of the one that opened by itself", async ({ page }) => {
    await handOff(page, WROTE);
    await expect(panelTitle(page, REPORT)).toBeVisible();

    await openButton(page, ANNEX).click();

    await expect(panelTitle(page, ANNEX)).toBeVisible();
    await expect(panelTitle(page, REPORT)).toHaveCount(0);
    // The other agent wrote it, so it opens to be read.
    await expect(page.locator(".canvas-panel .canvas-body")).toContainText("Số liệu");
  });
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("no canvas opens by itself, and a tap on a chip's Open covers the thread with that canvas", async ({ page }) => {
    await handOff(page, WROTE);
    await expect(chips(page)).toHaveCount(2);
    await expect(page.getByRole("region", { name: vi.canvas.button })).toHaveCount(0);

    await openButton(page, ANNEX).tap();

    await expect(page.getByRole("region", { name: vi.canvas.button })).toBeVisible();
    await expect(panelTitle(page, ANNEX)).toBeVisible();
  });
});
