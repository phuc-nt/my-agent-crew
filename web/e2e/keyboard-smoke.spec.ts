import { expect, test } from "@playwright/test";
import { type Conversation, defaultAgent, mockApi, run } from "./mock-api";

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

// The server expands "/name args" into the command's prompt, so what the list puts in the
// box, and what Enter then sends, must be exactly that shape.
test("'/' lists the agent's commands and Enter puts the chosen one in the box", async ({ page }) => {
  const commands = [
    { name: "tong-ket", description: "Tổng kết ngày", path: "/h/workspace/.claude/commands/tong-ket.md" },
    { name: "plan", description: "Lập kế hoạch", path: "/h/workspace/.claude/commands/plan.md" },
  ];
  const { posted } = await mockApi(page, {
    agents: [{ ...defaultAgent, commands }],
    conversations: [conversation("c1", "Chung")],
  });
  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: /Chung/ }).click();
  const box = page.getByRole("textbox", { name: /Nhắn cho agent/ });
  await box.click();

  await page.keyboard.type("/");
  const list = page.getByRole("listbox", { name: "Lệnh của agent" });
  await expect(list.getByRole("option")).toHaveCount(2);
  await page.keyboard.type("pl");
  await expect(list.getByRole("option")).toHaveCount(1);
  await page.keyboard.press("Enter");

  await expect(box).toHaveValue("/plan ");
  await expect(list).toHaveCount(0);
  await page.keyboard.type("tuần này");
  await page.keyboard.press("Enter");
  await expect
    .poll(() => posted.find((p) => p.path.endsWith("/messages"))?.body)
    .toEqual({ text: "/plan tuần này" });
});

// Esc only reaches the list from the box, so a list left open after a click elsewhere
// would sit over the thread with no key to put it away.
test("a click into the thread puts the command list away, and the box brings it back", async ({ page }) => {
  const commands = [{ name: "plan", description: "Lập kế hoạch", path: "/h/workspace/.claude/commands/plan.md" }];
  await mockApi(page, { agents: [{ ...defaultAgent, commands }], conversations: [conversation("c1", "Chung")] });
  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: /Chung/ }).click();
  const box = page.getByRole("textbox", { name: /Nhắn cho agent/ });
  await box.click();
  await page.keyboard.type("/");
  const list = page.getByRole("listbox", { name: "Lệnh của agent" });
  await expect(list).toBeVisible();

  await page.locator(".thread").first().click();
  await expect(list).toHaveCount(0);

  await box.click();
  await expect(list).toBeVisible();
});

test("the new-conversation shortcut opens one and the browser does not get the key", async ({ page }) => {
  const { conversations } = await mockApi(page, { conversations: [conversation("c1", "Cũ")] });
  await page.goto("/");
  await expect(page.getByRole("navigation").getByRole("button", { name: /Cũ/ })).toBeVisible();

  await page.keyboard.press("ControlOrMeta+n");

  await expect.poll(() => conversations.length).toBe(2);
});

// The strip only exists below the breakpoint where the activity folds under the thread.
test.describe("on a narrow screen", () => {
  test.use({ viewport: { width: 1024, height: 768 } });

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
});
