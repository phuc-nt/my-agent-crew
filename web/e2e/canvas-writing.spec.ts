import { expect, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { ASKED, ask, card, frame, piece } from "./writing-turn";

const PLAN = "00ff00ff00ff";
const TITLE = "Kế hoạch tuần";
const WRITE = { title: TITLE, kind: "markdown", content: "Việc một\n\nViệc hai" };
const text = vi.canvas.writing;

/** The call's arguments as the model writes them, in three pieces. */
const HEAD = '{"title":"Kế hoạch tuần","kind":"markdown","content":"Việc';
const MORE = " một\\n\\nViệc";
const LAST = ' hai"}';

const CALL = { id: "w1", name: "artifact_create", arguments: WRITE };
const ANSWER = {
  type: "assistant_message", message_id: "a1", content: "", provider: null, model: null, cost_usd: null,
  tool_calls: [CALL],
};
const STARTED = { type: "tool_call", tool_call_id: "w1", name: "artifact_create", arguments: WRITE };
const ENDED = {
  type: "tool_result", tool_call_id: "w1", name: "artifact_create", ok: true,
  output: `[artifact ${PLAN} v1]\nCanvas "${TITLE}" was created.`,
};

test.describe("on a wide screen", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("a canvas fills in beside the thread as the agent writes it, then gives way to the one it made", async ({ page }) => {
    const { box, canvas, turn } = await ask(page);

    await turn.push(piece(HEAD));
    await expect(card(page)).toContainText(TITLE);
    await expect(card(page)).toContainText(text.creating);
    await expect(frame(page)).toHaveCount(0);

    await turn.push(piece(MORE));
    await expect(frame(page)).toBeVisible();
    await expect(frame(page)).toContainText("Việc một");
    await expect(frame(page)).toContainText(text.unsaved);
    await expect(box).toBeFocused();
    // Beside the thread, not over it: the box keeps its place to the left of the frame.
    const typing = await box.boundingBox();
    const beside = await frame(page).boundingBox();
    expect((typing?.x ?? 0) + (typing?.width ?? 0)).toBeLessThanOrEqual(beside?.x ?? 0);

    await turn.push(piece(LAST));
    await expect(frame(page)).toContainText("Việc hai");

    canvas.add({ id: PLAN, title: TITLE, agent_id: "master", content: WRITE.content, conversationIds: ["c1"] });
    await turn.push(ANSWER, STARTED);
    await expect(frame(page)).toContainText(text.saving);
    await expect(card(page)).toHaveCount(0);

    await turn.push(ENDED);
    await expect(frame(page)).toHaveCount(0);
    await expect(page.getByRole("heading", { level: 2, name: TITLE })).toBeVisible();
    await expect(page.getByTestId("canvas-card")).toContainText(TITLE);
    await expect(box).toBeFocused();
    expect(await turn.posted()).toEqual([{ text: ASKED, request_id: expect.stringMatching(/^[0-9a-f]{32}$/) }]);
  });

  test("a page being written shows as its source, and nothing in it runs", async ({ page }) => {
    const { turn } = await ask(page);
    const head = '{"title":"Trang","kind":"html","content":"<script>window.pwned = 1</script>';
    const more = '<img src=\\"x\\" onerror=\\"window.pwned = 2\\"><b>đậm</b>';

    await turn.push(piece(head));
    await turn.push(piece(more));

    await expect(frame(page).locator("pre.canvas-code")).toHaveText(
      '<script>window.pwned = 1</script><img src="x" onerror="window.pwned = 2"><b>đậm</b>',
    );
    await expect(frame(page)).toContainText(text.source);
    await expect(page.locator("iframe")).toHaveCount(0);
    await expect(frame(page).locator("script, img, b")).toHaveCount(0);
    expect(await page.evaluate(() => (window as { pwned?: number }).pwned)).toBeUndefined();
  });

  test("a page being written as its source keeps its newest line in sight until the person scrolls up", async ({ page }) => {
    const { turn } = await ask(page);
    /** Lines `from + 1` to `to` of the page, as the model writes them inside the call's arguments. */
    const lines = (from: number, to: number) =>
      Array.from({ length: to - from }, (_, at) => `<p>dòng ${from + at + 1}</p>`).join("\\n");
    const line = (number: number) => frame(page).locator(`[data-line-start="${number}"]`);
    /** Long enough for the frame to have followed, had it meant to. */
    const drawn = () => page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))));

    await turn.push(piece(`{"title":"Trang","kind":"html","content":"${lines(0, 150)}`));
    await turn.push(piece(`\\n${lines(150, 300)}`));
    await expect(line(300)).toBeInViewport();
    await expect(line(1)).not.toBeInViewport();

    await turn.push(piece(`\\n${lines(300, 450)}`));
    await expect(line(450)).toBeInViewport();

    await frame(page).locator(".canvas-body").hover();
    await page.mouse.wheel(0, -3000);
    await expect(line(450)).not.toBeInViewport();
    await turn.push(piece(`\\n${lines(450, 600)}`));

    await expect(line(600)).toHaveText("<p>dòng 600</p>");
    await drawn();
    await expect(line(600)).not.toBeInViewport();
    await expect(line(450)).not.toBeInViewport();
  });
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("only the card shows until a tap, which covers the thread with the canvas being written", async ({ page }) => {
    const { turn } = await ask(page);
    await turn.push(piece(HEAD));
    await turn.push(piece(MORE));

    const show = page.getByRole("button", { name: text.showLabel(TITLE) });
    await expect(show).toBeVisible();
    await expect(frame(page)).toHaveCount(0);
    await expect(page.getByRole("region", { name: vi.canvas.button })).toHaveCount(0);
    expect((await show.boundingBox())?.height).toBeGreaterThanOrEqual(40);

    await show.tap();

    await expect(frame(page)).toBeVisible();
    await expect(frame(page)).toContainText("Việc một");
    const covers = await page.getByRole("region", { name: vi.canvas.button }).boundingBox();
    expect(covers).toMatchObject({ x: 0, y: 0, width: 390, height: 844 });
    const close = page.getByRole("button", { name: text.close });
    await expect(close).toBeFocused();
    expect((await close.boundingBox())?.height).toBeGreaterThanOrEqual(40);

    await turn.push(piece(LAST));
    await expect(frame(page)).toContainText("Việc hai");

    await page.keyboard.press("Escape");

    await expect(frame(page)).toHaveCount(0);
    await expect(page.getByRole("region", { name: vi.canvas.button })).toHaveCount(0);
    await expect(show).toBeFocused();

    // Opened from the keyboard and left by the frame's own button, it is the same way back.
    await page.keyboard.press("Enter");
    await expect(close).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(frame(page)).toHaveCount(0);
    await expect(show).toBeFocused();
  });
});
