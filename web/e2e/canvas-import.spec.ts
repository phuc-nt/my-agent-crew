import { expect, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeCanvas } from "../src/test/fake-canvas";
import { overflowing } from "./canvas-overflow";
import { type Conversation, mockApi } from "./mock-api";
import { smallTargets } from "./small-targets";

type Write = { method: string; path: string; body: unknown };

const { source } = vi.canvas;
const FILE = "workspace:default/notes/thuc-don.md";
const DEEP = "workspace:default/ghi chú của cả nhà/tuần này và tuần sau nữa/bữa sáng trưa tối/thuc-don.md";
const PAGE = "https://tin-tuc.example.com/bai-viet/thuc-don-ca-tuan?trang=2";

function chat(): Conversation {
  return {
    id: "c1", agent_id: "default", channel: "", title: "Bữa ăn", summary: "", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "idle", over_budget: false, parent_call_id: "", pending_approval: null,
    messages: [{ id: "m1", seq: 1, role: "user", content: "nhập thực đơn", context: "", tool_calls: [], tool_call_id: null, name: null, provider: null, model: null, cost_usd: null, created_at: "" }],
  };
}

/**
 * The app on a conversation whose one canvas an agent read from `from`, open on it as an agent's
 * canvas opens, to be read; each write the page sends is kept, in order.
 */
async function openImported(page: Page, from: string, file: string | null = null) {
  const fake = new FakeCanvas();
  fake.add({ title: "Thực đơn", content: "Sáng: phở\n", source: from, agent_id: "default", conversationIds: ["c1"] });
  if (file !== null) fake.files.put(from, file);
  await mockApi(page, { conversations: [chat()], canvas: fake });
  const writes: Write[] = [];
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname.replace(/^\/api/, "");
    if (/^\/artifacts\//.test(path) && ["PUT", "POST"].includes(request.method())) {
      writes.push({ method: request.method(), path, body: request.postDataJSON() });
    }
  });
  await page.goto("/#/chat/c1");
  await page.getByRole("button", { name: vi.canvas.buttonLabel(1) }).click();
  await page.locator(".canvas-row", { hasText: "Thực đơn" }).click();
  await expect(shown(page)).toHaveText("Sáng: phở");
  return { fake, writes };
}

const editor = (page: Page) => page.getByRole("textbox", { name: vi.canvas.editor });
const shown = (page: Page) => page.locator(".canvas-view");
const line = (page: Page) => page.locator(".canvas-source");
const again = (page: Page) => page.getByRole("button", { name: source.reimport, exact: true });
const height = async (page: Page, selector: string) => (await page.locator(selector).boundingBox())?.height ?? 0;

test.describe("a canvas read from a workspace file, beside a wide conversation", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("saves the typing first, then reads the file again on the version that save made", async ({ page }) => {
    const { fake, writes } = await openImported(page, FILE, "Sáng: bún\n");
    await expect(line(page).locator(".canvas-source-label")).toHaveText(source.label);
    await expect(line(page).locator(".canvas-source-path")).toHaveText("Agent/notes/thuc-don.md");
    await expect(line(page).locator(".canvas-source-path")).toHaveAttribute("title", "Agent/notes/thuc-don.md");

    await page.getByRole("button", { name: vi.canvas.edit, exact: true }).click();
    await editor(page).fill("Sáng: phở\nTrưa: cơm\n");
    await again(page).click();

    await expect(editor(page)).toHaveValue("Sáng: bún\n");
    await expect(page.locator(".canvas-notice[role=status]")).toHaveText(source.changed(3));
    await expect(page.locator(".canvas-version")).toContainText("v3 · bạn");
    expect(writes).toEqual([
      { method: "PUT", path: "/artifacts/a1", body: { content: "Sáng: phở\nTrưa: cơm\n", base_version: 1 } },
      { method: "POST", path: "/artifacts/a1/reimport", body: { base_version: 2 } },
    ]);
    // What the person typed is not lost: it is the version under the one the file became.
    expect(fake.canvases.get("a1")?.versions.map((version) => version.content)).toEqual([
      "Sáng: phở\n",
      "Sáng: phở\nTrưa: cơm\n",
      "Sáng: bún\n",
    ]);
  });

  test("says the file holds what the canvas does, and writes nothing", async ({ page }) => {
    const { fake, writes } = await openImported(page, FILE, "Sáng: phở\n");

    await again(page).click();

    await expect(page.locator(".canvas-notice[role=status]")).toHaveText(source.unchanged);
    expect(writes).toEqual([{ method: "POST", path: "/artifacts/a1/reimport", body: { base_version: 1 } }]);
    expect(fake.canvases.get("a1")?.versions).toHaveLength(1);
  });

  test("links the page a canvas was taken from, named by its host, in a tab that cannot reach back", async ({ page }) => {
    await openImported(page, PAGE);

    const link = page.getByRole("link", { name: source.open("tin-tuc.example.com") });
    await expect(link).toHaveAttribute("href", PAGE);
    await expect(link).toHaveAttribute("target", "_blank");
    await expect(link).toHaveAttribute("rel", "noopener noreferrer");
    await expect(again(page)).toHaveCount(0);
  });
});

test.describe("where a canvas came from, on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("keeps the name of the file in view and gives the folder up, with a button a finger can hit", async ({ page }) => {
    await openImported(page, DEEP, "Sáng: bún\n");

    await expect(page.locator(".canvas-source-file")).toHaveText("thuc-don.md");
    await expect(page.locator(".canvas-source-file")).toBeInViewport({ ratio: 1 });
    await expect(again(page)).toBeInViewport({ ratio: 1 });
    expect(await page.locator(".canvas-source-dir").evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true);
    expect(await height(page, ".canvas-source > button")).toBeGreaterThanOrEqual(40);
    expect(await smallTargets(page, ".canvas-dock")).toEqual([]);
    expect(await overflowing(page)).toEqual([]);

    // What the re-import says is held to the same width.
    await again(page).tap();
    await expect(page.locator(".canvas-notice[role=status]")).toHaveText(source.changed(2));
    await expect(shown(page)).toHaveText("Sáng: bún");
    expect(await smallTargets(page, ".canvas-dock")).toEqual([]);
    expect(await overflowing(page)).toEqual([]);
  });

  test("shows the link to a page as a control a finger can hit, inside the width", async ({ page }) => {
    await openImported(page, PAGE);

    await expect(page.getByRole("link", { name: source.open("tin-tuc.example.com") })).toBeInViewport({ ratio: 1 });
    expect(await height(page, ".canvas-source a")).toBeGreaterThanOrEqual(40);
    expect(await smallTargets(page, ".canvas-dock")).toEqual([]);
    expect(await overflowing(page)).toEqual([]);
  });
});
