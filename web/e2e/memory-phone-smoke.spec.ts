import { expect, type Page, test } from "@playwright/test";
import type { MemoryProposal, WikiPage } from "../src/api/types";
import { defaultAgent, mockApi } from "./mock-api";

// A phone, where a lost scroll position or a small target costs the most.
test.use({ viewport: { width: 390, height: 844 } });

function wikiPage(over: Partial<WikiPage>): WikiPage {
  return { slug: "han-eco", kind: "entities", title: "Hạn Eco", status: "ok", updated: "2026-09-25", sources: ["notes/2026-09-25.md"], questions: [], body: "", ...over };
}

async function openMemory(page: Page, tab: string) {
  await page.goto("/#/manage/memory");
  await page.getByRole("tab", { name: tab }).click();
}

test("a page followed from the bottom of a long one opens at its title, with focus there", async ({ page }) => {
  const long = Array.from({ length: 60 }, (_, i) => `Dòng ${i + 1} của ghi chép.`).join("\n\n");
  const vault = [
    wikiPage({ body: `${long}\n\nXem [[Trà sáng]].` }),
    wikiPage({ slug: "tra-sang", kind: "concepts", title: "Trà sáng", body: long }),
  ];
  await mockApi(page, { agents: [defaultAgent], wiki: { default: vault } });
  await openMemory(page, "Wiki");

  const section = page.getByTestId("wiki-section");
  await section.getByRole("button", { name: "Hạn Eco" }).click();
  const opened = section.getByTestId("wiki-page");
  const link = opened.getByRole("button", { name: "Trà sáng" });
  await link.scrollIntoViewIfNeeded();
  await link.press("Enter");

  const title = opened.getByRole("heading", { name: "Trà sáng" });
  await expect(title).toBeFocused();
  await expect(title).toBeInViewport();
  await expect(opened.getByRole("button", { name: /Về danh sách/ })).toBeInViewport();
});

/** Every element under `selector` whose right edge runs past the screen, i.e. text cut off. */
async function cutOff(page: Page, selector: string) {
  return page.evaluate((root) => {
    const offenders: string[] = [];
    for (const el of document.querySelectorAll(`${root}, ${root} *`)) {
      if (el.getBoundingClientRect().right > window.innerWidth + 1) offenders.push(`${el.tagName.toLowerCase()}.${el.className}`);
    }
    return offenders;
  }, selector);
}

test("an open question holding a long link wraps on a phone instead of running off the screen", async ({ page }) => {
  // No hyphen or slash past the host, so the browser finds no place of its own to break it.
  const question = "Link https://example.com/?token=Q2hlY2tUaGlzTGlua0lzU3RpbGxHb29kQmVmb3JlVXNpbmdJdEFnYWlu còn dùng được không?";
  await mockApi(page, { agents: [defaultAgent], wiki: { default: [wikiPage({ body: "Pha lúc 6h.", questions: [question] })] } });
  await openMemory(page, "Wiki");

  const section = page.getByTestId("wiki-section");
  await section.getByRole("button", { name: "Câu hỏi mở (1)" }).click();
  await expect(section.getByText(question)).toBeVisible();
  expect(await cutOff(page, ".wiki-open-questions")).toEqual([]);

  // The same question on its own page.
  await section.locator(".wiki-open-questions").getByRole("button", { name: "Hạn Eco" }).click();
  await expect(section.getByTestId("wiki-page").getByText(question)).toBeVisible();
  expect(await cutOff(page, "[data-testid=wiki-page]")).toEqual([]);
});

function proposal(over: Partial<MemoryProposal>): MemoryProposal {
  return {
    id: "p1",
    agent_id: "default",
    kind: "wiki_compile",
    name: "",
    description: "Dựng wiki",
    type: "",
    body: "",
    previous_body: "",
    status: "pending",
    source: "memory:wiki",
    reasons: "",
    created_at: "2026-09-26T01:00:00+00:00",
    resolved_at: null,
    ...over,
  };
}

test("the history toggle and a compiled page's disclosure are full touch targets that still look openable", async ({ page }) => {
  const planned = [{ slug: "tra-sang", kind: "concepts", title: "Trà sáng", body: "Pha lúc 6h.", sources: [], questions: [], status: "ok" }];
  const proposals = [proposal({ body: JSON.stringify(planned) })];
  await mockApi(page, { agents: [defaultAgent] });
  await page.route(/\/api\/memory\/proposals(\?.*)?$/, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ proposals }) }),
  );
  await openMemory(page, "Đề xuất");

  const section = page.getByTestId("memory-proposals");
  const summary = section.locator(".compile-page summary");
  await expect(summary).toHaveText("Xem nội dung");
  // A summary that is no longer a list item loses its triangle in Chromium and WebKit.
  expect(await summary.evaluate((el) => getComputedStyle(el).display)).toBe("list-item");
  expect((await summary.boundingBox())?.height).toBeGreaterThanOrEqual(40);

  const toggle = section.getByRole("button", { name: /Đã xử lý/ });
  expect((await toggle.boundingBox())?.height).toBeGreaterThanOrEqual(40);
});
