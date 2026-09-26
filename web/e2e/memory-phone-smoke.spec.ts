import { expect, type Page, test } from "@playwright/test";
import type { WikiPage } from "../src/api/types";
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
