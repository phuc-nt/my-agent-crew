import { expect, test } from "@playwright/test";
import { coachAgent, defaultAgent, mockApi, run } from "./mock-api";

const master = { ...defaultAgent, name: "Trợ lý", delegates: ["coach"] };
const MODEL = "Tuyến leo thang: Mô hình";
const SAVE = { name: "Lưu", exact: true } as const;

test("a way out for a stuck turn is set on an agent, held while it is no way out, and saved", async ({ page }) => {
  await mockApi(page, { agents: [master, coachAgent] });
  await page.goto("/#/manage/crew/coach");
  const editor = page.getByTestId("agent-editor");
  const block = editor.getByTestId("escalation-route");

  // Every agent starts without one, and the page says what that means.
  await expect(block.getByTestId("escalation-route-none")).toHaveText("Chưa đặt: lượt bị kẹt sẽ dừng như trước.");
  await block.getByRole("button", { name: "+ Đặt tuyến leo thang" }).click();
  await expect(block.getByTestId("escalation-route-none")).toHaveCount(0);

  // A row with no model is asked for one only when a save is tried.
  await expect(block.getByRole("alert")).toHaveCount(0);
  await editor.getByRole("button", SAVE).click();
  await expect(block.getByRole("alert")).toHaveText("Nhập tên mô hình, hoặc bỏ tuyến leo thang.");

  // The coach's own route is fake:echo: a turn stuck on it gains nothing from it.
  await block.getByLabel(MODEL).fill("echo");
  await expect(block.getByRole("alert")).toHaveText("Tuyến leo thang phải khác mọi tuyến ở trên.");
  await expect(block.getByLabel(MODEL)).toHaveAttribute("aria-invalid", "true");

  await block.getByLabel(MODEL).fill(" big ");
  await expect(block.getByRole("alert")).toHaveCount(0);
  const patch = page.waitForRequest((r) => r.method() === "PATCH" && /\/api\/agents\/coach$/.test(r.url()));
  await editor.getByRole("button", SAVE).click();
  expect((await patch).postDataJSON()).toEqual({ profile: { escalation_route: { provider: "fake", model: "big" } } });
  await expect(editor.getByRole("button", SAVE)).toBeDisabled();
  // A route takes effect on the agent's next turn: nothing asks for a restart.
  await expect(editor.getByTestId("restart-banner")).toHaveCount(0);

  // Reloading shows what the server kept.
  await page.reload();
  const kept = page.getByTestId("agent-editor").getByTestId("escalation-route");
  await expect(kept.getByLabel(MODEL)).toHaveValue("big");

  // Taking it away is saved as none, not as an empty row.
  await kept.getByRole("button", { name: "Bỏ tuyến leo thang" }).click();
  const cleared = page.waitForRequest((r) => r.method() === "PATCH" && /\/api\/agents\/coach$/.test(r.url()));
  await page.getByTestId("agent-editor").getByRole("button", SAVE).click();
  expect((await cleared).postDataJSON()).toEqual({ profile: { escalation_route: null } });
  await expect(kept.getByTestId("escalation-route-none")).toBeVisible();
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("the escalation row fits the screen and its boxes are big enough to tap and type in", async ({ page }) => {
    const coach = { ...coachAgent, escalation_route: { provider: "fake", model: "a-model-with-quite-a-long-name-v4-preview" } };
    await mockApi(page, { agents: [master, coach] });
    await page.goto("/#/manage/crew/coach");
    const block = page.getByTestId("agent-editor").getByTestId("escalation-route");
    await block.scrollIntoViewIfNeeded();

    const model = block.getByLabel(MODEL);
    await expect(model).toHaveValue("a-model-with-quite-a-long-name-v4-preview");
    // Safari zooms the page into any field under 16px when it takes focus.
    expect(await model.evaluate((el) => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16);
    for (const control of [model, block.getByLabel("Tuyến leo thang: Nhà cung cấp"), block.getByRole("button", { name: "Bỏ tuyến leo thang" })]) {
      const box = (await control.boundingBox())!;
      expect(box.height).toBeGreaterThanOrEqual(40);
      expect(box.x + box.width).toBeLessThanOrEqual(390);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  });
});

test("a turn that moved to its escalation route says so above the box, by what stopped it", async ({ page }) => {
  const answered = (id: string) => [
    { type: "assistant_message", message_id: id, content: "Đã xong.", tool_calls: [], provider: "fake", model: "big", cost_usd: 0 },
    { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
  ];
  await mockApi(page, { turns: [
    [
      { type: "route_fallback", provider: "fake", model: "echo", error: "HTTP 502" },
      { type: "escalated", reason: "error", provider: "fake", model: "big", error: "every route failed" },
      ...answered("a1"),
    ],
    [{ type: "escalated", reason: "loop", provider: "fake", model: "big", error: "" }, ...answered("a2")],
  ] });
  await page.goto("/");

  await page.getByRole("textbox").fill("một");
  await page.keyboard.press("Enter");
  const notice = page.getByTestId("notice");
  await expect(notice).toHaveText("Không tuyến chính nào trả lời; phần còn lại của lượt chạy trên tuyến leo thang fake:big.");
  await expect(notice).toHaveClass("notice escalated");
  await expect(page.getByTestId("message-assistant")).toHaveText(/Đã xong\./);

  await page.getByRole("textbox").fill("hai");
  await page.keyboard.press("Enter");
  await expect(notice).toHaveText("Lượt này gọi cùng một lệnh nhiều lần liên tiếp; phần còn lại chạy trên tuyến leo thang fake:big.");
});

test("a run's timeline names the move, why it was made, and the model that answered after it", async ({ page }) => {
  const moved = run({
    id: "moved",
    agent_id: "coach",
    source: "job:coach/brief",
    summary: "Đã xong trên tuyến leo thang",
    steps: [
      { kind: "fallback", provider: "fake", model: "echo", error: "HTTP 502", duration_ms: 800 },
      { kind: "escalation", reason: "error", provider: "fake", model: "big", error: "every route failed — fake:echo: HTTP 502", duration_ms: 1500 },
      { kind: "model", provider: "fake", model: "big", cost_usd: 0.004, duration_ms: 2100 },
    ],
  });
  await mockApi(page, { agents: [defaultAgent, coachAgent], runs: [moved], stream: [{ type: "snapshot", runs: [] }] });
  await page.goto("/");
  await page.getByRole("button", { name: /Quản lý/ }).click();

  const card = page.getByTestId("manage-screen").getByTestId("run-card").filter({ hasText: "Đã xong trên tuyến leo thang" });
  // A finished run is one line until it is opened.
  await card.locator(".run-summary").click();
  const steps = card.getByTestId("run-step");
  await expect(steps).toHaveCount(3);
  const step = steps.nth(1);
  await expect(step).toHaveClass(/\bescalation\b/);
  await expect(step).toContainText("fake:big");
  await expect(step).toContainText("leo thang");
  await expect(step).toContainText("Không tuyến chính nào trả lời.");
  await expect(step).toContainText("every route failed — fake:echo: HTTP 502");
  await expect(step).toHaveAttribute("data-state", "done");
  // The move is not one more route that failed: it reads apart from the step above it.
  await expect(steps.first()).toHaveClass(/\bfallback\b/);
  await expect(steps.first()).not.toContainText("leo thang");
});
