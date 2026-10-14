// What `computer_screenshot` says it saw, read the one way everywhere.
//
// The tool answers with a first line the server words one of two ways: the picture was saved
// at a path, or the screen is unchanged since the frame the conversation was last shown. A
// run's step keeps a one-line preview of that answer cut at 160 characters, so the end of the
// line cannot be the anchor. The expressions are the server's own, character for character:
// `tests/test_desktop_routes.py` pins them against the whole answer and against the preview.
// A frame id is `<16 hex>-<width>x<height>-<display>`: the size of the picture is in the id.
import type { StoredMessage } from "../api/types";

const FRAME = "[0-9a-f]{16}-\\d{1,10}x\\d{1,10}-\\d{1,10}";
const FRAME_ONLY = new RegExp(`^${FRAME}$`);
const SAVED_LINE = new RegExp(`^Đã chụp màn hình và lưu vào (.*?(${FRAME})\\.png)\\. frame_id: `);
const UNCHANGED_LINE = new RegExp(`^Màn hình không đổi từ lần chụp trước\\. frame_id: (${FRAME}) `);
const SIZE = /^[0-9a-f]{16}-(\d+)x(\d+)-/;

export const SCREENSHOT_TOOL = "computer_screenshot";
/** Where the helper's pictures go, under the workspace or under the agent's first write path. */
const FOLDER = "desktop";

/** A frame's picture, by frame id: what the screenshots in reach said they saved. */
export type FramePaths = ReadonlyMap<string, string>;

/** Whether a value is a frame id, the whole of it and nothing around it. */
export function isFrame(value: unknown): value is string {
  return typeof value === "string" && FRAME_ONLY.test(value);
}

/** The picture's size in pixels as its id names it, or null where it names none to divide by. */
export function frameSize(frame: string): { width: number; height: number } | null {
  const found = SIZE.exec(frame);
  if (!found) return null;
  const width = Number(found[1]);
  const height = Number(found[2]);
  return width > 0 && height > 0 ? { width, height } : null;
}

/** The picture a screenshot saved and its frame, or null: for any other tool, even one whose
 *  answer happens to read the same, and for an answer that names no picture. */
export function savedShot(toolName: string, output: string | null | undefined): { path: string; frame: string } | null {
  if (toolName !== SCREENSHOT_TOOL || !output) return null;
  const found = SAVED_LINE.exec(output);
  return found ? { path: found[1], frame: found[2] } : null;
}

/** The frame a screenshot said is still on the screen, or null. Its picture is the one an
 *  earlier saved line of the same frame named. */
export function unchangedFrame(toolName: string, output: string | null | undefined): string | null {
  if (toolName !== SCREENSHOT_TOOL || !output) return null;
  return UNCHANGED_LINE.exec(output)?.[1] ?? null;
}

/**
 * Where a frame's picture is when no screenshot in reach names it: the tool's folder in the
 * workspace, or under the first of the agent's write paths. The server judges that folder
 * where it really is; this reads the path as written, which is the same for any path that
 * goes through no link. A write path written whole stays whole: the files route takes a path
 * from the root as long as it lands in the workspace, as the server's folder must.
 */
export function folderPath(frame: string, writePaths: readonly string[] | undefined): string {
  const first = writePaths?.[0] ?? "";
  const parts: string[] = [];
  for (const part of first.split("/")) {
    if (part === "" || part === ".") continue;
    if (part === "..") parts.pop();
    else parts.push(part);
  }
  const path = [...parts, FOLDER, `${frame}.png`].join("/");
  return first.startsWith("/") ? `/${path}` : path;
}

/** Every frame a list of screenshot answers saved, with its path; a later one wins. */
export function framePaths(answers: Iterable<{ name: string; output: string | null | undefined }>): FramePaths {
  const found = new Map<string, string>();
  for (const { name, output } of answers) {
    const shot = savedShot(name, output);
    if (shot) found.set(shot.frame, shot.path);
  }
  return found;
}

/**
 * Where a conversation's messages say a frame's picture was saved, and when: the screenshot
 * that saved it. A tool's answer is matched to the call that asked for it, so a message of
 * another tool that reads the same names nothing.
 */
export function savedInMessages(messages: readonly StoredMessage[], frame: string): { path: string; at: string } | null {
  const called = new Map<string, string>();
  let found: { path: string; at: string } | null = null;
  for (const m of messages) {
    for (const call of m.tool_calls ?? []) called.set(call.id, call.name);
    if (m.role !== "tool") continue;
    const name = (m.tool_call_id !== null && called.get(m.tool_call_id)) || m.name || "";
    const shot = savedShot(name, m.content);
    if (shot?.frame === frame) found = { path: shot.path, at: m.created_at };
  }
  return found;
}
