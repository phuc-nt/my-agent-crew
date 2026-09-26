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
