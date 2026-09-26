import { expect, test } from "@playwright/test";
import { type Conversation, coachAgent, defaultAgent, mockApi, run } from "./mock-api";

// A phone, not a narrow desktop window: the width people actually hold.
test.use({ viewport: { width: 390, height: 844 } });

function conversation(id: string, title: string): Conversation {
  return {
    id,
    agent_id: "default",
    channel: "",
    title,
    summary: "",
    created_at: "",
    updated_at: "",
    autonomous: false,
    cost_cap_usd: 1,
    skills: [],
    auto_approve: [],
    spent_usd: 0,
    unknown_cost_calls: 0,
    status: "idle",
    over_budget: false,
    parent_call_id: "",
    messages: [],
    pending_approval: null,
  };
}

const older = run({ id: "older", agent_id: "coach", title: "Dọn kho", summary: "Đã xong hôm qua" });

/**
 * Nothing may be wider than the screen.
 *
 * A single over-wide element gives the whole page a horizontal scrollbar, and
 * then every tap-target drifts as the person scrolls sideways looking for it.
 * Asserting on the document's own scroll width catches that wherever it comes
 * from, which a per-element width assertion would not.
 */
async function widestOverflow(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    const offenders: string[] = [];
    for (const el of document.querySelectorAll("*")) {
      const box = el.getBoundingClientRect();
      if (box.width > window.innerWidth + 1 && box.height > 0) {
        offenders.push(`${el.tagName.toLowerCase()}.${String(el.className).split(" ")[0]}`);
      }
    }
    return { scrollWidth: document.documentElement.scrollWidth, width: window.innerWidth, offenders };
  });
}

test("the conversation takes the whole screen and the list slides in over it", async ({ page }) => {
  await mockApi(page, {
    agents: [defaultAgent, coachAgent],
    runs: [],
    conversations: [conversation("c1", "Chung"), conversation("c2", "Ôn thi")],
  });
  await page.goto("/");

  // The thread and the composer own the screen; the list waits behind the menu button,
  // the way every messaging app on the phone already works.
  const sidebar = page.locator(".sidebar");
  await expect(page.getByRole("textbox", { name: /^Nhắn cho agent/ })).toBeVisible();
  await expect(sidebar).toBeHidden();

  const overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);

  // Opened, the list is wholly on screen, and picking a conversation puts it away again.
  const menu = page.getByRole("button", { name: "Mở danh sách cuộc trò chuyện" });
  await menu.click();
  await expect(sidebar).toBeVisible();
  await expect.poll(async () => (await sidebar.boundingBox())?.x).toBe(0);
  await sidebar.getByRole("button", { name: /Ôn thi/ }).click();
  await expect(sidebar).toBeHidden();
  await expect(page.locator(".conversation-header")).toContainText("Ôn thi");

  // Escape closes it as well, and the keyboard lands back on the button that opened it
  // rather than on a control inside a panel nobody can see.
  await menu.click();
  await expect(sidebar).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(sidebar).toBeHidden();
  await expect(menu).toBeFocused();
});

// The search box lives in the drawer, and a closed drawer is inert: a browser refuses to
// focus anything inside it, so the shortcut has to open the drawer around the box first.
test("the search shortcut opens the list at the search box", async ({ page }) => {
  const many = Array.from({ length: 9 }, (_, i) => conversation(`c${i}`, `Cuộc ${i}`));
  await mockApi(page, { agents: [defaultAgent, coachAgent], runs: [], conversations: many });
  await page.goto("/");
  await expect(page.getByRole("textbox", { name: /^Nhắn cho agent/ })).toBeVisible();

  await page.keyboard.press("ControlOrMeta+k");

  await expect(page.locator(".sidebar")).toBeVisible();
  await expect(page.getByRole("searchbox")).toBeFocused();
  // While the list covers the chat, the chat takes no focus: Tab stays in the list.
  await expect(page.locator("main")).toHaveAttribute("inert", "");
});

test("the manage sections stay reachable when the nav has no room to stack", async ({ page }) => {
  await mockApi(page, { agents: [defaultAgent, coachAgent], runs: [older] });
  await page.goto("/#/manage/activity");

  // The nav turns into one scrolling row; every section must still be clickable.
  await expect(page.getByTestId("manage-screen")).toBeVisible();
  await page.getByRole("button", { name: /Đội/ }).click();
  await expect(page).toHaveURL(/#\/manage\/crew/);

  const overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);
});

test("a run opened on its own still fits, timeline and all", async ({ page }) => {
  await mockApi(page, { agents: [defaultAgent, coachAgent], runs: [older] });
  await page.goto("/#/manage/activity/older");

  await expect(page.getByTestId("run-replay")).toBeVisible();
  const overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);
});

test("connections fit, keys, host defaults and an open key field included", async ({ page }) => {
  await mockApi(page, { agents: [defaultAgent, coachAgent] });
  await page.goto("/#/manage/connections");

  // Opened, a row is at its widest: the field and its two buttons share one line.
  const router = page.getByTestId("credential-OPENROUTER_API_KEY");
  await router.getByRole("button", { name: "Thay" }).click();
  await expect(router.getByLabel("Giá trị cho OPENROUTER_API_KEY")).toBeVisible();
  await expect(page.getByTestId("credential-OLLAMA_BASE_URL")).toContainText("11434");

  const overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);
});

test("the activity log's chips wrap on a phone and stay big enough to tap", async ({ page }) => {
  const runs = [
    older,
    run({ id: "web", source: "chat", status: "error", title: "Trả lời" }),
    run({ id: "tg", source: "telegram", status: "halted", title: "Nhắn Telegram" }),
    run({ id: "wiki", agent_id: "coach", source: "memory:wiki", title: "Sổ tay" }),
    run({ id: "sub", source: "delegate:c9", title: "Việc được giao" }),
    run({ id: "api", source: "api", title: "Gọi API" }),
  ];
  await mockApi(page, { agents: [defaultAgent, coachAgent], runs });
  await page.goto("/#/manage/activity");

  // Every group is on screen at once; a row that scrolled sideways would hide choices.
  const filters = page.getByTestId("run-filters");
  await expect(filters.getByRole("button", { name: "Giao việc" })).toBeVisible();
  for (const chip of await filters.getByRole("button").all()) {
    const box = await chip.boundingBox();
    expect(box?.height).toBeGreaterThanOrEqual(40);
    expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(390);
  }

  // Narrowed to nothing, the way out is the one button in the empty box.
  await filters.getByRole("group", { name: "Agent" }).getByRole("button", { name: coachAgent.name }).click();
  await filters.getByRole("group", { name: "Trạng thái" }).getByRole("button", { name: /^đã dừng$/i }).click();
  const clear = page.getByTestId("run-log").getByRole("button", { name: "Bỏ lọc" });
  expect((await clear.boundingBox())?.height).toBeGreaterThanOrEqual(40);

  const overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);
});

// The widest the costs page gets: every figure in the millions, a long model id, the
// cache columns and the tiles two to a row. None of it may push the page sideways.
test("the costs page fits, cache columns and today's tiles included", async ({ page }) => {
  const usage = {
    calls: 1_234,
    cost_usd: 12.3456,
    prompt_tokens: 123_456_789,
    completion_tokens: 9_876_543,
    cached_tokens: 98_765_432,
    unknown_cost_calls: 3,
  };
  const days = Array.from({ length: 7 }, (_, i) => ({ day: `2026-09-${20 + i}`, ...usage }));
  const models = [
    { model: "openrouter:deepseek/deepseek-v4-flash-preview-2026-09", ...usage },
    { model: "ollama:qwen3", ...usage, cached_tokens: 0 },
  ];
  const call = {
    kind: "model",
    chars: 120,
    provider: "openrouter",
    model: "deepseek-v4-flash",
    cost_usd: 0.0012,
    tool_calls: ["read_file", "shell_run"],
    first_token_ms: 1_234,
    prompt_tokens: 45_678,
    cached_tokens: 40_000,
    thinking: true,
    duration_ms: 3_000,
  };
  const runs = [run({ id: "a", agent_id: "coach", steps: [call] }), run({ id: "b", steps: [call, call] })];
  const stats = {
    runs: 500,
    model_calls: 12_345,
    spent_usd: 123.45,
    unknown_cost_calls: 3,
    by_agent: { coach: 100, default: 23.45 },
    by_model: {},
    by_day: {},
    days,
    models,
    pending_proposals: 0,
  };
  await mockApi(page, { agents: [defaultAgent, coachAgent], runs, stats });
  await page.goto("/#/manage/costs");

  await expect(page.getByTestId("stat-periods")).toContainText("Hôm nay");
  await expect(page.getByTestId("stat-periods")).toContainText("7 ngày");
  await expect(page.getByTestId("stat-models")).toContainText("98.8M · 80%");
  await expect(page.getByTestId("stat-agent-cache")).toContainText("40k · 88%");
  await expect(page.getByTestId("stats")).toContainText("500 lượt gần nhất");
  let overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);

  // The step's usage line is the longest line a run card carries.
  await page.goto("/#/manage/activity/a");
  await expect(page.getByTestId("run-replay")).toContainText("TTFT 1.2s · 45.7k tok (40k cache) · suy nghĩ");
  overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);
});

// Hidden or saying "no runs", a chat whose stored runs could not be read would pass for
// one that never ran.
test("a chat whose run history cannot be read says so, with a retry big enough to tap", async ({ page }) => {
  await mockApi(page, { agents: [defaultAgent, coachAgent], runs: [], conversations: [conversation("c1", "Chung")] });
  await page.route(/\/api\/activity\/runs\?.*conversation_id=/, (route) => route.abort());
  await page.goto("/#/chat/c1");

  const strip = page.getByTestId("conversation-activity");
  await expect(strip).toContainText("Không tải được lịch sử chạy.");
  const box = await strip.getByRole("button", { name: "Thử lại" }).boundingBox();
  expect(box?.height).toBeGreaterThanOrEqual(40);

  const overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);
});
