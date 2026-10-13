import { describe, expect, it } from "vitest";
import { browserCallLine } from "./browser-call";

const act = (args: Record<string, unknown>) => browserCallLine("browser_act", { ref: "e12", ...args });

describe("a waiting browser call said in one line", () => {
  it("names the host of the page a navigation opens, and nothing else of the address", () => {
    expect(browserCallLine("browser_navigate", { url: "https://shop.example/orders?id=7#top" })).toBe("Mở trang shop.example");
    expect(browserCallLine("browser_navigate", { url: "http://localhost:8080/x", tab: "don" })).toBe("Mở trang localhost:8080");
  });

  it("shows the address as written, cut, when it does not parse or names no host", () => {
    expect(browserCallLine("browser_navigate", { url: "shop.example/cart" })).toBe("Mở trang shop.example/cart");
    expect(browserCallLine("browser_navigate", { url: "about:blank" })).toBe("Mở trang about:blank");
    const long = `not a url ${"x".repeat(200)}`;
    expect(browserCallLine("browser_navigate", { url: long })).toBe(`Mở trang ${long.slice(0, 80)}…`);
  });

  it("reads nothing from a navigation that names no address", () => {
    expect(browserCallLine("browser_navigate", {})).toBeNull();
    expect(browserCallLine("browser_navigate", { url: "   " })).toBeNull();
    expect(browserCallLine("browser_navigate", { url: 7 })).toBeNull();
  });

  it("says what each kind of action does to which element", () => {
    expect(act({ kind: "click", name: "Thanh toán" })).toBe("Bấm «Thanh toán»");
    expect(act({ kind: "type", name: "Tìm kiếm", text: "sách cũ" })).toBe("Gõ «sách cũ» vào «Tìm kiếm»");
    expect(act({ kind: "fill", name: "Email", text: "a@b.example" })).toBe("Điền «a@b.example» vào «Email»");
    expect(act({ kind: "press", name: "Tìm kiếm", key: "Enter" })).toBe("Nhấn Enter tại «Tìm kiếm»");
    expect(act({ kind: "select", name: "Số lượng", value: "2" })).toBe("Chọn «2» ở «Số lượng»");
    expect(act({ kind: "hover", name: "Tài khoản" })).toBe("Rê chuột lên «Tài khoản»");
    expect(act({ kind: "scroll", name: "Chân trang" })).toBe("Cuộn tới «Chân trang»");
    expect(act({ kind: "upload", name: "Chọn tệp", path: "out/hoa-don.pdf" })).toBe("Tải tệp out/hoa-don.pdf lên «Chọn tệp»");
  });

  it("keeps an empty text as an empty quote: clearing a field is an action too", () => {
    expect(act({ kind: "fill", name: "Ghi chú", text: "" })).toBe("Điền «» vào «Ghi chú»");
    expect(act({ kind: "fill", name: "Ghi chú" })).toBe("Điền «» vào «Ghi chú»");
  });

  it("reads nothing from an action of an unknown kind or one that names no element", () => {
    expect(act({ kind: "drag", name: "Thẻ" })).toBeNull();
    expect(act({ name: "Thẻ" })).toBeNull();
    expect(act({ kind: "click" })).toBeNull();
    expect(act({ kind: "click", name: "   " })).toBeNull();
    expect(act({ kind: "click", name: { text: "Thẻ" } })).toBeNull();
  });

  it("reads nothing from a key press with no key or an upload with no file", () => {
    expect(act({ kind: "press", name: "Tìm kiếm" })).toBeNull();
    expect(act({ kind: "upload", name: "Chọn tệp" })).toBeNull();
  });

  it("puts a value on one line and cuts each one at eighty characters", () => {
    expect(act({ kind: "click", name: "Đặt\n  hàng\tngay " })).toBe("Bấm «Đặt hàng ngay»");
    const name = "n".repeat(81);
    const text = "t".repeat(200);
    expect(act({ kind: "type", name, text })).toBe(`Gõ «${"t".repeat(80)}…» vào «${"n".repeat(80)}…»`);
    // Exactly eighty fits, so nothing is said to be cut.
    expect(act({ kind: "click", name: "n".repeat(80) })).toBe(`Bấm «${"n".repeat(80)}»`);
  });

  it("writes a character that reorders or hides text as its code point", () => {
    expect(act({ kind: "click", name: "Huỷ‮áoX" })).toBe("Bấm «Huỷ[U+202E]áoX»");
    expect(act({ kind: "click", name: "Gử​i" })).toBe("Bấm «Gử[U+200B]i»");
  });

  it("returns text as it is, markup included, for the page to draw as text", () => {
    expect(act({ kind: "click", name: "<img src=x onerror=alert(1)>" })).toBe("Bấm «<img src=x onerror=alert(1)>»");
  });

  it("reads nothing from any other tool, whatever its arguments look like", () => {
    expect(browserCallLine("write_file", { url: "https://shop.example", kind: "click", name: "Mua" })).toBeNull();
    expect(browserCallLine("browser_snapshot", { tab: "don" })).toBeNull();
    expect(browserCallLine("browser_navigate_now", { url: "https://shop.example" })).toBeNull();
  });

  it("reads nothing from arguments that are not a mapping", () => {
    expect(browserCallLine("browser_navigate", "url=https://shop.example")).toBeNull();
    expect(browserCallLine("browser_navigate", null)).toBeNull();
    expect(browserCallLine("browser_act", ["click"])).toBeNull();
  });
});
