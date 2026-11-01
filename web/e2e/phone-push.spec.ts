import { expect, type Page, test } from "@playwright/test";
import { mockApi } from "./mock-api";

test.use({ viewport: { width: 390, height: 844 } });

// Headless Chromium has no push service and reports notifications as denied whatever is
// granted, so both are played in the page; the service worker and the screen are real.
async function fakePushService(page: Page) {
  await page.addInitScript(() => {
    let permission: NotificationPermission = "default";
    Object.defineProperty(Notification, "permission", { get: () => permission });
    Notification.requestPermission = async () => (permission = "granted");
    let held: object | null = null;
    PushManager.prototype.getSubscription = async () => held as PushSubscription | null;
    PushManager.prototype.subscribe = async (options?: PushSubscriptionOptionsInit) => {
      const endpoint = "https://push.example/device";
      held = {
        endpoint,
        options,
        toJSON: () => ({ endpoint, keys: { p256dh: "p", auth: "a" } }),
        unsubscribe: async () => ((held = null), true),
      };
      return held as PushSubscription;
    };
  });
}

test("the inbox turns notifications on for this phone and sends a test", async ({ page }) => {
  await fakePushService(page);
  await mockApi(page);
  const asked: string[] = [];
  await page.route(/\/api\/push\//, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    asked.push(`${request.method()} ${path}`);
    const body = path.endsWith("/key") ? { key: "BAEC" } : path.endsWith("/test") ? { status: 201 } : { subscribed: true };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto("/#/inbox");

  // Off is the first thing the inbox shows, ahead of what waits in it.
  const card = page.getByRole("region", { name: "Thông báo" });
  await expect(page.locator("main.inbox-body > :first-child")).toHaveAttribute("aria-label", "Thông báo");

  await card.getByRole("button", { name: "Bật thông báo" }).click();
  await expect(card.getByRole("button", { name: "Gửi thử" })).toBeVisible();
  expect(asked).toContain("POST /api/push/subscriptions");
  const registered = await page.evaluate(async () => (await navigator.serviceWorker.getRegistration("/"))?.active?.scriptURL);
  expect(registered).toMatch(/\/sw\.js$/);

  await card.getByRole("button", { name: "Gửi thử" }).click();
  await expect(card.getByRole("status")).toHaveText("Đã gửi. Thông báo sẽ hiện trong giây lát.");
  expect(asked).toContain("POST /api/push/test");
});
