import { describe, expect, it } from "vitest";
import { slugify, splitRelated, wikiSlugFromHref } from "./wiki-links";

describe("slugify", () => {
  // Each expected value is what the server's wiki slug function returns for the same
  // input; a mismatch would point a link at a page the vault files under another name.
  it.each([
    ["Hạn Eco", "han-eco"],
    ["Đà Lạt", "da-lat"],
    ["ĐỒNG HỒ", "dong-ho"],
    ["Sức khoẻ & Thể thao", "suc-khoe-the-thao"],
    ["Café 2026", "cafe-2026"],
    ["  Trà  sáng ", "tra-sang"],
    ["naïve—résumé", "naive-resume"],
    ["ふびん", "ふびん"],
    ["東京タワー", "東京タワー"],
    ["ガ", "ガ"],
    ["!!!", "khong-ten"],
  ])("slugs %j as the server does", (title, slug) => {
    expect(slugify(title)).toBe(slug);
  });
});

describe("splitRelated", () => {
  it("separates the machine's related block from what the author wrote", () => {
    const body = [
      "Hạn nộp là thứ tư. Xem [[Trà sáng]].",
      "",
      "<!-- wiki:related -->",
      "",
      "## Liên quan",
      "",
      "Trang này nhắc tới: [[tra-sang]]",
      "Được nhắc tới ở: [[da-lat]], [[tra-sang]]",
      "",
      "<!-- /wiki:related -->",
      "",
    ].join("\n");
    expect(splitRelated(body)).toEqual({
      authored: "Hạn nộp là thứ tư. Xem [[Trà sáng]].",
      related: ["tra-sang", "da-lat"],
    });
  });

  it("leaves a body with no block as the author wrote it", () => {
    expect(splitRelated("  Chỉ có chữ.\n")).toEqual({ authored: "Chỉ có chữ.", related: [] });
  });
});

describe("wikiSlugFromHref", () => {
  it("reads the slug back out of a rendered link, decoding what the renderer encoded", () => {
    expect(wikiSlugFromHref("#wiki/han-eco")).toBe("han-eco");
    expect(wikiSlugFromHref(`#wiki/${encodeURIComponent("ふびん")}`)).toBe("ふびん");
    expect(wikiSlugFromHref("https://example.com")).toBeNull();
    expect(wikiSlugFromHref(undefined)).toBeNull();
  });
});
