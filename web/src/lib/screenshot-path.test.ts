import { describe, expect, it } from "vitest";
import { screenshotLabel, screenshotPath } from "./screenshot-path";

const SHOT = "browser_screenshot";
const saved = (label: string, path: string) => `Đã lưu ảnh chụp tab ${label} vào ${path}.`;

/** A run's step keeps its output this way: whitespace collapsed, cut at 160 characters. */
const preview = (output: string) => output.replace(/\s+/g, " ").trim().slice(0, 160);

describe("the path a screenshot was saved at", () => {
  it("is read from the first line of the tool's answer", () => {
    const whole = `${saved("don", "screenshots/20261013T120000Z-don.png")}\nKích thước 1280x720, 48 KB.`;
    expect(screenshotPath(SHOT, whole)).toBe("screenshots/20261013T120000Z-don.png");
    expect(screenshotPath(SHOT, saved("don", "out/screenshots/20261013T120000Z-don-2.jpg"))).toBe("out/screenshots/20261013T120000Z-don-2.jpg");
    expect(screenshotPath(SHOT, saved("tab_1", "20261013T120000Z-tab_1.png"))).toBe("20261013T120000Z-tab_1.png");
  });

  it("is read the same from a step's one-line preview, where the line has no end", () => {
    const whole = `${saved("don", "screenshots/20261013T120000Z-don.png")}\n\n${"Trang dài. ".repeat(40)}`;
    const line = preview(whole);
    expect(line).toHaveLength(160);
    expect(line).not.toContain("\n");
    expect(screenshotPath(SHOT, line)).toBe("screenshots/20261013T120000Z-don.png");
  });

  it("stops at the first name the tool gives, in a folder whose own name has dots", () => {
    expect(screenshotPath(SHOT, saved("don", "out/v1.2/20261013T120000Z-don.png"))).toBe("out/v1.2/20261013T120000Z-don.png");
    const twice = `${saved("don", "a/20261013T120000Z-don.png")} Bản trước: a/20261012T120000Z-don.png.`;
    expect(screenshotPath(SHOT, twice)).toBe("a/20261013T120000Z-don.png");
  });

  it("is nothing for an answer that names no picture", () => {
    expect(screenshotPath(SHOT, "Không chụp được: tab đã đóng.")).toBeNull();
    expect(screenshotPath(SHOT, saved("don", "screenshots/anh.png"))).toBeNull();
    expect(screenshotPath(SHOT, saved("don", "screenshots/20261013T120000Z-don.gif"))).toBeNull();
    // The line has to open the answer: a mention further down is not the tool's own word.
    expect(screenshotPath(SHOT, `Ghi chú.\n${saved("don", "screenshots/20261013T120000Z-don.png")}`)).toBeNull();
    // A preview cut before the name ended names no file to ask for.
    expect(screenshotPath(SHOT, "Đã lưu ảnh chụp tab don vào screenshots/20261013T1200")).toBeNull();
    expect(screenshotPath(SHOT, "")).toBeNull();
    expect(screenshotPath(SHOT, null)).toBeNull();
    expect(screenshotPath(SHOT, undefined)).toBeNull();
  });

  it("is nothing for any other tool, even one whose answer reads the same", () => {
    const line = saved("don", "screenshots/20261013T120000Z-don.png");
    expect(screenshotPath("shell_run", line)).toBeNull();
    expect(screenshotPath("browser_snapshot", line)).toBeNull();
    expect(screenshotPath("mcp__x__browser_screenshot", line)).toBeNull();
  });
});

describe("the tab a screenshot was taken of", () => {
  it("is the label the line names", () => {
    expect(screenshotLabel(saved("don-2", "screenshots/20261013T120000Z-don-2.png"))).toBe("don-2");
  });

  it("is empty for a line that names none", () => {
    expect(screenshotLabel("Không chụp được.")).toBe("");
  });
});
