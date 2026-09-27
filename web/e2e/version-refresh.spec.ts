import { expect, test } from "@playwright/test";
import { mockApi } from "./mock-api";

// The dev server runs source modules, so the check is inert there. These tests make the
// page look built — loaded from a hashed entry — and the server serve another one, the
// way the phone's installed app sees a server restarted on a new bundle.
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    new MutationObserver((_, observer) => {
      if (!document.head) return;
      observer.disconnect();
      const entry = document.createElement("script");
      entry.type = "module";
      entry.src = "/assets/index-old.js";
      document.head.append(entry);
    }).observe(document, { childList: true, subtree: true });
  });
  await page.route(/\/assets\/index-old\.js$/, (route) => route.fulfill({ body: "", contentType: "text/javascript" }));
  // Only the check's own fetch of the page: the navigation to it stays with the dev server.
  await page.route(/^https?:\/\/[^/]+\/$/, (route) =>
    route.request().resourceType() === "fetch"
      ? route.fulfill({ body: '<script type="module" src="/assets/index-new.js"></script>', contentType: "text/html" })
      : route.fallback(),
  );
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("a newer build on the server offers a thumb-sized reload that fits the screen", async ({ page }) => {
    await mockApi(page);
    await page.goto("/");
    const bar = page.getByTestId("update-bar");
    await expect(bar).toContainText("Có bản mới");
    const reload = bar.getByRole("button", { name: "Tải lại để dùng bản mới" });
    expect((await reload.boundingBox())!.height).toBeGreaterThanOrEqual(40);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);

    await page.evaluate(() => ((window as unknown as { beforeReload: boolean }).beforeReload = true));
    await reload.click();
    await expect
      .poll(() => page.evaluate(() => (window as unknown as { beforeReload?: boolean }).beforeReload))
      .toBeUndefined();
  });
});

// The page is named only by a look that found the server serving it; one already on
// another build leaves the page unnamed rather than lending it its own version. Loaded
// again while the server serves the page's own entry, it is named.
test("settings name the server's build, and the page's once the server serves it", async ({ page }) => {
  await mockApi(page);
  await page.goto("/#/manage/settings");
  await expect(page.getByTestId("settings-versions")).toHaveText("Máy chủ 0.8.0");

  await page.route(/^https?:\/\/[^/]+\/$/, (route) =>
    route.request().resourceType() === "fetch"
      ? route.fulfill({ body: '<script type="module" src="/assets/index-old.js"></script>', contentType: "text/html" })
      : route.fallback(),
  );
  await page.reload();
  await expect(page.getByTestId("settings-versions")).toHaveText("Giao diện 0.8.0 · Máy chủ 0.8.0");
});
