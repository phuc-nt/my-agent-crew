// Where `browser_screenshot` says it saved its picture.
//
// The tool answers with a first line the server words as "Đã lưu ảnh chụp tab {label} vào
// {path}.", and a run's step keeps only a one-line preview of that answer, cut at 160
// characters, so the end of the line cannot be the anchor. The expression is the server's
// own, character for character: `tests/test_browser_routes.py` pins it (`SHOT_LINE`) against
// the whole answer and against the step preview.
const SHOT_LINE = /^Đã lưu ảnh chụp tab [a-z0-9_-]+ vào (.*?\d{8}T\d{6}Z-[a-z0-9_-]+\.(?:png|jpg))\./;

/** The label the same line names, for the picture's caption. */
const SHOT_LABEL = /^Đã lưu ảnh chụp tab ([a-z0-9_-]+) vào /;

const SCREENSHOT_TOOL = "browser_screenshot";

/**
 * The picture's path, relative to the agent's workspace, or null: for any other tool, even
 * one whose answer happens to read the same, and for an answer that names no picture.
 * Whether the call succeeded is the caller's to check.
 */
export function screenshotPath(toolName: string, output: string | null | undefined): string | null {
  if (toolName !== SCREENSHOT_TOOL || !output) return null;
  return SHOT_LINE.exec(output)?.[1] ?? null;
}

/** The tab the picture was taken of, as the agent named it; "" when the line names none. */
export function screenshotLabel(output: string): string {
  return SHOT_LABEL.exec(output)?.[1] ?? "";
}
