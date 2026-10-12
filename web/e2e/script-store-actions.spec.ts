import { type Dialog, expect, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeScriptStore } from "../src/test/fake-script-store";
import { coachAgent, type Conversation, defaultAgent, mockApi } from "./mock-api";

// What a person does on the script store: delete a key or a whole namespace after being
// asked, follow a namespace to the job or the conversation it belongs to, and come and go
// by the address. A real browser decides where the keyboard is once a row has left the page.

const { scriptStore: words } = vi;
const STORE = '[data-testid="script-store"]';
const BRIEF = 'lịch "Bản tin sáng"';

const STORED = { tool_calls: [], tool_call_id: null, name: null, cost_usd: null, created_at: "", provider: null, model: null };
const chat: Conversation = {
  id: "c1", agent_id: "coach", channel: "", title: "Đơn tháng mười", summary: "", created_at: "", updated_at: "",
  autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
  status: "idle", over_budget: false, parent_call_id: "", pending_approval: null,
  messages: [{ ...STORED, id: "1", seq: 1, role: "assistant", content: "Đã ghi lại ba đơn.", provider: "fake", model: "echo" }],
};
const briefJob = {
  ...coachAgent.schedules[0], id: "coach/brief", schedule_id: "brief", agent_id: "coach",
  next_run: null, last_run: null, running: false, paused: false,
};

/** Three keys under the coach's schedule, one under a conversation of its own, two under a
 *  schedule it no longer declares, one under a name of neither kind; one key for the master. */
function seeded(): FakeScriptStore {
  const store = new FakeScriptStore();
  store.keep("coach", "job:brief", "a", 1).keep("coach", "job:brief", "b", 2).keep("coach", "job:brief", "c", 3);
  store.keep("coach", "conv:c1", "cursor", "m-17");
  store.keep("coach", "job:retired", "x", 1).keep("coach", "job:retired", "y", 2);
  store.keep("coach", "misc", "note", null);
  store.keep("default", "misc", "of-master", true);
  return store;
}

async function open(page: Page, store: FakeScriptStore, address = "/#/manage/memory/scripts/coach") {
  await mockApi(page, { agents: [defaultAgent, coachAgent], conversations: [chat], jobs: [briefJob], scriptStore: store });
  await page.goto(address);
}

/** Answers every question the page asks, and keeps what it asked. */
function answering(page: Page, agree: boolean): string[] {
  const asked: string[] = [];
  page.on("dialog", (dialog: Dialog) => {
    asked.push(`${dialog.type()}: ${dialog.message()}`);
    void (agree ? dialog.accept() : dialog.dismiss());
  });
  return asked;
}

const card = (page: Page, namespace: string) => page.locator(`[data-namespace="${namespace}"]`);
const keys = (page: Page) => page.locator(".script-store-key").allTextContents();
const said = (page: Page) => page.locator(STORE).getByRole("status");
/** The button that shows one key's value; exact, as one key may begin with another. */
const view = (page: Page, key: string) => page.getByRole("button", { name: words.viewLabel(key), exact: true });

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test.describe(`acting on the script store at ${viewport.width}px`, () => {
    test.use({ viewport });

    test("deleting a key asks first, takes the row out and puts the keyboard on the next key", async ({ page }) => {
      const store = seeded();
      const asked = answering(page, true);
      await open(page, store);

      await card(page, "job:brief").getByRole("button", { name: words.deleteKeyLabel("b"), exact: true }).click();

      await expect(said(page)).toHaveText(words.deletedKey("b"));
      expect(asked).toEqual([`confirm: ${words.deleteKeyConfirm("b", BRIEF)}`]);
      await expect(card(page, "job:brief").getByTestId("script-store-entry")).toHaveCount(2);
      expect(store.keys("coach", "job:brief")).toEqual(["a", "c"]);
      await expect(view(page, "c")).toBeFocused();

      // The last key has none after it: the keyboard goes to the one before.
      await card(page, "job:brief").getByRole("button", { name: words.deleteKeyLabel("c"), exact: true }).click();
      await expect(said(page)).toHaveText(words.deletedKey("c"));
      await expect(view(page, "a")).toBeFocused();
    });

    test("a no to the question deletes nothing", async ({ page }) => {
      const store = seeded();
      const asked = answering(page, false);
      await open(page, store);

      await card(page, "job:brief").getByRole("button", { name: words.deleteKeyLabel("b"), exact: true }).click();
      await card(page, "job:retired").getByRole("button", { name: words.deleteAllLabel('lịch "retired"') }).click();

      expect(asked).toHaveLength(2);
      await expect(said(page)).toBeEmpty();
      expect(store.keys("coach", "job:brief")).toEqual(["a", "b", "c"]);
      expect(store.keys("coach", "job:retired")).toEqual(["x", "y"]);
      expect(await keys(page)).toEqual(["cursor", "a", "b", "c", "x", "y", "note"]);
    });

    test("deleting a namespace names how many keys go, and the keyboard lands on the heading that took its place", async ({ page }) => {
      const store = seeded();
      const asked = answering(page, true);
      await open(page, store);
      const retired = card(page, "job:retired");
      await expect(retired.getByText(words.orphan)).toBeVisible();

      await retired.getByRole("button", { name: words.deleteAllLabel('lịch "retired"') }).click();

      await expect(said(page)).toHaveText(words.deletedAll(2, 'lịch "retired"'));
      expect(asked).toEqual([`confirm: ${words.deleteAllConfirm(2, 'lịch "retired"')}`]);
      await expect(retired).toHaveCount(0);
      expect(store.keys("coach", "job:retired")).toEqual([]);
      await expect(card(page, "misc").getByRole("heading")).toBeFocused();
      expect(await keys(page)).toEqual(["cursor", "a", "b", "c", "note"]);
    });

    test("a key that is gone when its value is asked for leaves the list, and the keyboard goes to the next key", async ({ page }) => {
      const store = seeded();
      await open(page, store);
      const gone = view(page, "b");
      await expect(gone).toBeVisible();
      // A script deleted it since the list was read.
      store.route("/agents/coach/script-store", "DELETE", new URLSearchParams({ namespace: "job:brief", key: "b" }));

      await gone.press("Enter");

      await expect(said(page)).toHaveText(words.gone("b"));
      await expect(gone).toHaveCount(0);
      await expect(view(page, "c")).toBeFocused();
    });

    test("a schedule's namespace leads to its job's row, and a conversation's to the conversation", async ({ page }) => {
      await open(page, seeded());

      const toJob = card(page, "job:brief").getByRole("link", { name: "Bản tin sáng" });
      await expect(toJob).toHaveAttribute("href", "#/manage/jobs/coach%2Fbrief");
      // Neither a schedule that is gone nor a name of neither kind has anywhere to lead.
      await expect(card(page, "job:retired").getByRole("link")).toHaveCount(0);
      await expect(card(page, "misc").getByRole("link")).toHaveCount(0);
      await toJob.click();
      await expect(page).toHaveURL(/#\/manage\/jobs\/coach%2Fbrief$/);
      await expect(page.getByTestId("job").filter({ hasText: "Bản tin sáng" })).toBeFocused();

      await page.goBack();
      await expect(page).toHaveURL(/#\/manage\/memory\/scripts\/coach$/);
      await card(page, "conv:c1").getByRole("link", { name: "Đơn tháng mười" }).click();
      await expect(page).toHaveURL(/#\/chat\/c1$/);
      await expect(page.getByTestId("message-assistant")).toContainText("Đã ghi lại ba đơn.");
    });

    test("is opened from the memory screen by the keyboard, follows the agent chosen, and Back returns tab by tab", async ({ page }) => {
      await open(page, seeded(), "/#/manage/memory");
      await page.getByRole("tab", { name: vi.memory.agents }).click();

      await page.getByRole("tab", { name: words.tab }).press("Enter");
      await expect(page).toHaveURL(/#\/manage\/memory\/scripts\/default$/);
      await expect(page.getByRole("tab", { name: words.tab })).toHaveAttribute("aria-selected", "true");
      await expect.poll(() => keys(page)).toEqual(["of-master"]);

      await page.locator(STORE).getByRole("combobox", { name: vi.agents }).selectOption("coach");
      await expect(page).toHaveURL(/#\/manage\/memory\/scripts\/coach$/);
      await expect.poll(() => keys(page)).toEqual(["cursor", "a", "b", "c", "x", "y", "note"]);

      await page.goBack();
      await expect.poll(() => keys(page)).toEqual(["of-master"]);
      await page.goBack();
      await expect(page).toHaveURL(/#\/manage\/memory$/);
      await expect(page.getByRole("tab", { name: vi.memory.agents })).toHaveAttribute("aria-selected", "true");
      await expect(page.locator(STORE)).toHaveCount(0);
    });
  });
}
