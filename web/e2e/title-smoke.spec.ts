import { expect, test } from "@playwright/test";
import { mockApi } from "./mock-api";

/** A conversation the first sentence has already named, as the sidebar lists it. */
const named = {
  id: "c1", agent_id: "default", channel: "", title: "Giúp tôi lập kế hoạch", created_at: "", updated_at: "",
  autonomous: false, cost_cap_usd: 5, spent_usd: 0, unknown_cost_calls: 0, status: "idle", over_budget: false,
  summary: "", skills: [], auto_approve: [], parent_call_id: "", messages: [], pending_approval: null,
};

test("a title the server writes after the turn reaches the sidebar over the stream", async ({ page }) => {
  await mockApi(page, {
    conversations: [{ ...named }],
    stream: [
      { type: "snapshot", runs: [] },
      { type: "conversation", conversation: { ...named, title: "Kế hoạch ôn thi cuối kỳ" } },
    ],
  });
  await page.goto("/");
  const nav = page.getByRole("navigation");
  // The renamed row replaces the listed one whichever of the two arrives first, so the
  // assertion is on the end state rather than on a moment in the load.
  await expect(nav.getByRole("button", { name: /Kế hoạch ôn thi cuối kỳ/ })).toBeVisible();
  await expect(nav.getByRole("button", { name: /Giúp tôi lập kế hoạch/ })).toHaveCount(0);
});

test("renaming happens where the title is shown, and is sent to the server", async ({ page }) => {
  const { conversations } = await mockApi(page, { conversations: [{ ...named }] });
  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: /Giúp tôi lập kế hoạch/ }).click();

  const heading = page.getByRole("heading", { level: 1 });
  await heading.getByRole("button").click();
  // The old name arrives selected, so typing replaces it.
  await page.keyboard.type("Ôn thi cuối kỳ");
  await page.keyboard.press("Enter");

  await expect(heading).toContainText("Ôn thi cuối kỳ");
  await expect(page.getByRole("navigation")).toContainText("Ôn thi cuối kỳ");
  // The PATCH reached the server, not just the screen.
  expect(conversations[0].title).toBe("Ôn thi cuối kỳ");
});

test("Escape abandons a rename and leaves the name alone", async ({ page }) => {
  const { conversations } = await mockApi(page, { conversations: [{ ...named }] });
  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: /Giúp tôi lập kế hoạch/ }).click();

  const heading = page.getByRole("heading", { level: 1 });
  await heading.getByRole("button").click();
  await page.keyboard.type("Tên nháp");
  await page.keyboard.press("Escape");

  await expect(heading).toContainText("Giúp tôi lập kế hoạch");
  expect(conversations[0].title).toBe("Giúp tôi lập kế hoạch");
});
