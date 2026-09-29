import { expect, type Route, test } from "@playwright/test";
import { mockApi, sse } from "./mock-api";

/**
 * Holds the tab's own turn open on a stream this test can push frames onto whenever it
 * likes, the way `chat-smoke.spec.ts`'s "Stop on an approved call" test drives one call by
 * hand: `page.route()` cannot do this, since one call answers with its whole body at once
 * and a queue/steer scenario needs the first call still open while later calls happen.
 * Every other request — the create, and every POST after the first send — goes to the real
 * `fetch` and is free to reach Playwright's own routes, including `mockApi`'s.
 */
async function holdTheFirstTurn(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
    const realFetch = window.fetch.bind(window);
    const frame = (e: Record<string, unknown> & { type: string }) =>
      new TextEncoder().encode(`event: ${e.type}\r\ndata: ${JSON.stringify(e)}\r\n\r\n`);
    let claimed = false;
    window.fetch = async (input, init) => {
      const url = String(input instanceof Request ? input.url : input);
      if (claimed || !/\/api\/conversations\/[^/]+\/messages$/.test(url)) return realFetch(input, init);
      claimed = true;
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          (window as unknown as { pushToHeldTurn: (e: object) => void }).pushToHeldTurn = (e) => {
            try {
              controller.enqueue(frame(e as Record<string, unknown> & { type: string }));
            } catch {
              // The turn already closed — Stop, most likely — so there is nothing left to push onto.
            }
          };
          (window as unknown as { closeHeldTurn: () => void }).closeHeldTurn = () => controller.close();
        },
      });
      return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
    };
  });
}

async function pushToHeldTurn(page: import("@playwright/test").Page, event: object) {
  await page.evaluate((e) => (window as unknown as { pushToHeldTurn: (e: object) => void }).pushToHeldTurn(e), event);
}

/**
 * Answers every POST to `/messages` after the held one with a single `queued` event, and
 * mirrors it onto the conversation's own `queued` array — the one thing a per-test route has
 * to do that the base mock cannot, since only this route knows which text just arrived and
 * what kind it queues as. Mirroring here is what makes the central `stop` route (in
 * `mock-api.ts`) and a reload's `GET` both see the same queue the chips are drawn from.
 */
async function queueEverythingAfter(page: import("@playwright/test").Page, conv: { queued?: import("../src/api/types").QueuedMessage[] }) {
  let nextId = 1;
  await page.route(/\/api\/conversations\/[^/]+\/messages$/, async (route: Route) => {
    const { text } = route.request().postDataJSON() as { text: string };
    const kind: "steer" | "follow_up" = text.trim().startsWith("/steer") ? "steer" : "follow_up";
    const item = { id: nextId, kind, text };
    nextId += 1;
    conv.queued = [...(conv.queued ?? []), item];
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sse([{ type: "queued", item_id: item.id, kind: item.kind, position: (conv.queued?.length ?? 1) - 1 }]),
    });
  });
}

test.describe("sending while the conversation is busy", () => {
  test("a plain message queues as a chip, clears the box, and leaves Stop and send both showing", async ({ page }) => {
    await holdTheFirstTurn(page);
    const mock = await mockApi(page, {});
    await page.goto("/");
    await page.getByRole("textbox").fill("bắt đầu việc này");
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("thinking")).toBeVisible();
    await queueEverythingAfter(page, mock.conversations[0]);

    await page.getByRole("textbox").fill("thêm một việc nữa");
    await page.keyboard.press("Enter");

    const chip = page.locator(".queued-chip");
    await expect(chip).toHaveCount(1);
    await expect(chip).toContainText("Đã xếp hàng, chạy sau lượt này");
    await expect(chip).toContainText("thêm một việc nữa");
    await expect(page.getByRole("textbox")).toHaveValue("");
    await expect(page.getByRole("button", { name: "Dừng" })).toBeVisible();
  });

  test("a /steer message queues as a chip that will cut in, then becomes a user message once the held turn steers it", async ({ page }) => {
    await holdTheFirstTurn(page);
    const mock = await mockApi(page, {});
    await page.goto("/");
    await page.getByRole("textbox").fill("tìm tài liệu giúp tôi");
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("thinking")).toBeVisible();
    await queueEverythingAfter(page, mock.conversations[0]);

    await page.getByRole("textbox").fill("/steer đổi hướng nhé");
    await page.keyboard.press("Enter");
    await expect(page.locator(".queued-chip")).toContainText("Sẽ chèn vào lượt đang chạy");

    // The turn already running reads the queue before its next model call and folds the
    // steer in — this is that moment, on the same stream the first send opened.
    await pushToHeldTurn(page, { type: "steer", text: "đổi hướng nhé", count: 1 });
    await pushToHeldTurn(page, {
      type: "assistant_message", message_id: "a1", content: "Đã đổi hướng.",
      tool_calls: [], provider: "fake", model: "echo", cost_usd: 0,
    });
    await pushToHeldTurn(page, { type: "done", spent_usd: 0.02, unknown_cost_calls: 0 });

    await expect(page.getByTestId("message-user").last()).toContainText("đổi hướng nhé");
    await expect(page.locator(".queued-chip")).toHaveCount(0);
  });

  test("Stop hands both queued texts back to the box in order and the chips go", async ({ page }) => {
    await holdTheFirstTurn(page);
    const mock = await mockApi(page, {});
    await page.goto("/");
    await page.getByRole("textbox").fill("việc một");
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("thinking")).toBeVisible();
    await queueEverythingAfter(page, mock.conversations[0]);

    await page.getByRole("textbox").fill("việc hai");
    await page.keyboard.press("Enter");
    await page.getByRole("textbox").fill("/steer việc ba");
    await page.keyboard.press("Enter");
    await expect(page.locator(".queued-chip")).toHaveCount(2);

    await page.getByRole("button", { name: "Dừng" }).click();
    await expect(page.locator(".queued-chip")).toHaveCount(0);
    await expect(page.getByRole("textbox")).toHaveValue("việc hai\n\n/steer việc ba");
  });

  test("a reload still shows the chip: the conversation's own queued field carries it", async ({ page }) => {
    await holdTheFirstTurn(page);
    const mock = await mockApi(page, {});
    await page.goto("/");
    await page.getByRole("textbox").fill("việc để lâu");
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("thinking")).toBeVisible();
    await queueEverythingAfter(page, mock.conversations[0]);

    await page.getByRole("textbox").fill("việc chờ thêm");
    await page.keyboard.press("Enter");
    await expect(page.locator(".queued-chip")).toHaveCount(1);

    const convId = mock.conversations[0].id;
    await page.goto(`/#/chat/${convId}`);
    await expect(page.locator(".queued-chip")).toHaveCount(1);
    await expect(page.locator(".queued-chip")).toContainText("việc chờ thêm");
  });
});

test.describe("busy composer density at 390px", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("chips wrap instead of forcing the page wider, and Stop and send stay tappable", async ({ page }) => {
    await holdTheFirstTurn(page);
    const mock = await mockApi(page, {});
    await page.goto("/");
    await page.getByRole("textbox").fill("một việc dài để xem chip có xuống dòng không nhé bạn ơi");
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("thinking")).toBeVisible();
    await queueEverythingAfter(page, mock.conversations[0]);

    await page.getByRole("textbox").fill("một việc dài để xem chip có xuống dòng không nhé bạn ơi");
    await page.keyboard.press("Enter");
    await page.getByRole("textbox").fill("/steer một việc chèn cũng dài không kém để chắc chắn nó xuống dòng");
    await page.keyboard.press("Enter");

    const chips = page.locator(".queued-chip");
    await expect(chips).toHaveCount(2);
    const first = await chips.nth(0).boundingBox();
    const second = await chips.nth(1).boundingBox();
    expect(first).not.toBeNull();
    expect(second).not.toBeNull();
    // Wrapped onto its own line rather than squeezed beside the first on one row.
    expect(second!.y).toBeGreaterThan(first!.y);

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);

    // Both actions show at once here: the box holds text, so send is offered beside Stop.
    await page.getByRole("textbox").fill("thêm chữ");
    for (const name of ["Dừng", "Xếp hàng"]) {
      const box = await page.getByRole("button", { name }).boundingBox();
      expect(box).not.toBeNull();
      expect(box!.width).toBeGreaterThanOrEqual(44);
      expect(box!.height).toBeGreaterThanOrEqual(44);
    }
  });
});
