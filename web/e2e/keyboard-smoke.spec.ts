import { expect, test } from "@playwright/test";
import { type Conversation, mockApi, run } from "./mock-api";

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

/** Enough threads that the sidebar offers a search box at all. */
const many = Array.from({ length: 9 }, (_, i) => conversation(`c${i}`, `Cuộc ${i}`));

test("the search shortcut puts the cursor in the box without touching the mouse", async ({ page }) => {
  await mockApi(page, { conversations: many });
  await page.goto("/");
  const search = page.getByRole("searchbox");
  await expect(search).toBeVisible();

  await page.keyboard.press("ControlOrMeta+k");

  await expect(search).toBeFocused();
  // And it is a working box once focused, not just a focused one.
  await page.keyboard.type("Cuộc 3");
  await expect(page.getByRole("navigation").getByRole("button", { name: /Cuộc 3/ })).toHaveCount(1);
  await expect(page.getByRole("navigation").getByRole("button", { name: /Cuộc 4/ })).toHaveCount(0);
});

test("the new-conversation shortcut opens one and the browser does not get the key", async ({ page }) => {
  const { conversations } = await mockApi(page, { conversations: [conversation("c1", "Cũ")] });
  await page.goto("/");
  await expect(page.getByRole("navigation").getByRole("button", { name: /Cũ/ })).toBeVisible();

  await page.keyboard.press("ControlOrMeta+n");

  await expect.poll(() => conversations.length).toBe(2);
});

test("escape closes the activity strip, and typing in a field keeps it open", async ({ page }) => {
  await mockApi(page, {
    conversations: [conversation("c1", "Có hoạt động")],
    runs: [run({ conversation_id: "c1", status: "done" })],
  });
  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: /Có hoạt động/ }).click();

  const strip = page.getByTestId("conversation-activity");
  const toggle = strip.getByRole("button", { expanded: false });
  await toggle.click();
  const opened = strip.getByRole("button", { expanded: true });
  await expect(opened).toBeVisible();

  // Escape with the cursor in the composer belongs to the composer: a half-typed message
  // is not a reason to rearrange the screen around it.
  await page.getByRole("textbox", { name: /Nhắn cho agent/ }).click();
  await page.keyboard.press("Escape");
  await expect(opened).toBeVisible();

  await page.getByRole("heading").first().click();
  await page.keyboard.press("Escape");
  await expect(strip.getByRole("button", { expanded: false })).toBeVisible();
});
