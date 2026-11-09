import { expect, test, type Page } from "@playwright/test";
import { flatPng } from "./flat-png";
import { mockApi } from "./mock-api";

const PNG = flatPng(40, 30);
const LINE = (path: string) => `[Tệp đính kèm đã lưu: ${path}]`;

/** The agent's inbox: takes the body as the file and serves it back from the files route. */
async function inbox(page: Page) {
  const saved: string[] = [];
  await page.route(/\/api\/agents\/[^/]+\/inbox\?/, async (route) => {
    const name = new URL(route.request().url()).searchParams.get("name") ?? "file";
    const path = `/h/agents/default/workspace/inbox/20261109-120000-${name}`;
    saved.push(path);
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ path, line: LINE(path) }) });
  });
  await page.route(/\/api\/agents\/[^/]+\/files\?/, (route) => route.fulfill({ status: 200, contentType: "image/png", body: PNG }));
  return saved;
}

const reply = [
  { type: "assistant_message", message_id: "a1", content: "Thấy ảnh rồi.", tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
  { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
];

test("a photo picked with the paperclip goes with the message and shows in the thread", async ({ page }) => {
  const mock = await mockApi(page, { turns: [reply] });
  const saved = await inbox(page);
  await page.goto("/");
  await page.getByTestId("attach-input").setInputFiles({ name: "anh.png", mimeType: "image/png", buffer: PNG });
  await expect(page.getByTestId("composer-file")).toHaveClass(/ready/);
  await page.getByRole("textbox").fill("xem giúp");
  await page.keyboard.press("Enter");

  await expect(page.getByTestId("message-user").getByTestId("attachment-image")).toBeVisible();
  await expect(page.getByTestId("message-user")).toContainText("xem giúp");
  await expect(page.getByTestId("composer-file")).toHaveCount(0);
  const sent = mock.posted.map((p) => JSON.stringify(p.body)).find((body) => body.includes("xem giúp"));
  expect(sent).toContain(JSON.stringify(`${LINE(saved[0])}\nxem giúp`).slice(1, -1));
});

test("a screenshot pasted into the box joins the message on a phone too", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page, { turns: [reply] });
  await inbox(page);
  await page.goto("/");
  await page.getByRole("textbox").focus();
  await page.evaluate((bytes) => {
    const data = new DataTransfer();
    data.items.add(new File([new Uint8Array(bytes)], "image.png", { type: "image/png" }));
    document.querySelector("textarea")!.dispatchEvent(new ClipboardEvent("paste", { clipboardData: data, bubbles: true }));
  }, Array.from(PNG));
  await expect(page.getByTestId("composer-file")).toHaveClass(/ready/);
  const attach = page.getByRole("button", { name: "Đính kèm ảnh hoặc tệp" });
  const send = page.getByRole("button", { name: "Gửi" });
  await expect(attach).toBeVisible();
  // The tray sits inside the box without pushing the buttons off a phone's width.
  expect((await send.boundingBox())!.x + 44).toBeLessThanOrEqual(390);
  await send.click();
  await expect(page.getByTestId("message-user").getByTestId("attachment-image")).toBeVisible();
  await expect(page.getByTestId("message-assistant")).toContainText("Thấy ảnh rồi.");
});
