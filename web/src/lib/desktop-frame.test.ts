// What a `computer_screenshot` answer says it saw, read the one way from the whole answer and
// from the one line a run's step keeps of it. The answers below are the server's sentences
// (`texts_desktop.py`) and the preview is cut as `activity/step_previews.py` cuts it.
import { describe, expect, it } from "vitest";
import type { StoredMessage } from "../api/types";
import { SCREENSHOT_TOOL, folderPath, frameSize, framePaths, isFrame, savedInMessages, savedShot, unchangedFrame } from "./desktop-frame";

const FRAME = "00000000000000a1-1456x910-1";
const LATER = "00000000000000a2-1456x910-1";
/** The folder of an agent that keeps its pictures deep, as the server's own test has it. */
const DEEP = "records/kept/for/the/owner/by/this/agent";

const saved = (path: string, frame = FRAME) =>
  `Đã chụp màn hình và lưu vào ${path}. frame_id: ${frame} (1456×910; toạ độ của computer_act tính theo điểm ảnh của ảnh này).\nỨng dụng phía trước: Notes`;
const unchanged = (path: string, frame = FRAME) =>
  `Màn hình không đổi từ lần chụp trước. frame_id: ${frame} (1456×910); ảnh đã lưu ở ${path} vẫn đúng. Muốn hỏi về ảnh thì gọi lại kèm \`question\`.`;

/** What a run's step keeps of an answer: one line, cut at 160 characters. */
function preview(text: string): string {
  const flat = text.split(/\s+/).filter(Boolean).join(" ");
  const chars = [...flat];
  return chars.length <= 160 ? flat : `${chars.slice(0, 160).join("")}…`;
}

describe("a frame id", () => {
  it("is the whole value and nothing around it", () => {
    expect(isFrame(FRAME)).toBe(true);
    for (const wrong of [` ${FRAME}`, `${FRAME}.png`, "00000000000000A1-1456x910-1", "a1-1456x910-1", "", 7, null, undefined]) {
      expect(isFrame(wrong)).toBe(false);
    }
  });

  it("names the size of its picture, and none it could divide by when a side is nought", () => {
    expect(frameSize(FRAME)).toEqual({ width: 1456, height: 910 });
    expect(frameSize("00000000000000a1-0x910-1")).toBeNull();
    expect(frameSize("00000000000000a1-1456x0-1")).toBeNull();
    expect(frameSize("not a frame")).toBeNull();
  });
});

describe("a screenshot's answer", () => {
  it.each([
    ["the workspace's folder", `desktop/${FRAME}.png`],
    ["a deep write path", `${DEEP}/desktop/${FRAME}.png`],
  ])("names the picture it saved under %s, whole and as a step keeps it", (_where, path) => {
    for (const read of [saved(path), preview(saved(path))]) expect(savedShot(SCREENSHOT_TOOL, read)).toEqual({ path, frame: FRAME });
    expect(preview(saved(path))).toHaveLength(161);
  });

  it.each([
    ["the workspace's folder", `desktop/${FRAME}.png`, true],
    ["a deep write path", `${DEEP}/desktop/${FRAME}.png`, false],
  ])("names the frame still on screen under %s, whole and as a step keeps it", (_where, path, pathKept) => {
    for (const read of [unchanged(path), preview(unchanged(path))]) expect(unchangedFrame(SCREENSHOT_TOOL, read)).toBe(FRAME);
    // Why the frame is the anchor: a step's line ends before a deep path.
    expect(preview(unchanged(path)).includes(path)).toBe(pathKept);
  });

  it("is read only as one or the other", () => {
    const path = `desktop/${FRAME}.png`;
    expect(savedShot(SCREENSHOT_TOOL, unchanged(path))).toBeNull();
    expect(unchangedFrame(SCREENSHOT_TOOL, saved(path))).toBeNull();
  });

  it("names nothing when it says neither, or says it later than its first words", () => {
    const later = [`Ghi chú: ${saved(`desktop/${FRAME}.png`)}`, `Ghi chú: ${unchanged(`desktop/${FRAME}.png`)}`];
    for (const read of ["Màn hình của máy đang khoá.", "", null, undefined, ...later]) {
      expect(savedShot(SCREENSHOT_TOOL, read)).toBeNull();
      expect(unchangedFrame(SCREENSHOT_TOOL, read)).toBeNull();
    }
    // A saved line whose picture is not named after a frame names no picture.
    expect(savedShot(SCREENSHOT_TOOL, saved("desktop/picture.png"))).toBeNull();
  });

  it("of another tool names nothing, even one that reads the same", () => {
    expect(savedShot("read_file", saved(`desktop/${FRAME}.png`))).toBeNull();
    expect(unchangedFrame("computer_state", unchanged(`desktop/${FRAME}.png`))).toBeNull();
  });
});

describe("where a frame's picture is", () => {
  it("is the tool's folder of the workspace, or under the agent's first write path", () => {
    expect(folderPath(FRAME, undefined)).toBe(`desktop/${FRAME}.png`);
    expect(folderPath(FRAME, [])).toBe(`desktop/${FRAME}.png`);
    expect(folderPath(FRAME, [DEEP, "other"])).toBe(`${DEEP}/desktop/${FRAME}.png`);
  });

  it("reads a write path as the server does: its dots walked, a path from the root kept whole", () => {
    expect(folderPath(FRAME, ["./records//kept/"])).toBe(`records/kept/desktop/${FRAME}.png`);
    expect(folderPath(FRAME, ["records/old/../kept"])).toBe(`records/kept/desktop/${FRAME}.png`);
    expect(folderPath(FRAME, ["."])).toBe(`desktop/${FRAME}.png`);
    expect(folderPath(FRAME, ["/Users/owner/ws/records"])).toBe(`/Users/owner/ws/records/desktop/${FRAME}.png`);
  });

  it("is what the screenshots in reach saved, the later one winning", () => {
    const found = framePaths([
      { name: SCREENSHOT_TOOL, output: saved(`desktop/${FRAME}.png`) },
      { name: SCREENSHOT_TOOL, output: preview(saved(`${DEEP}/desktop/${LATER}.png`, LATER)) },
      { name: SCREENSHOT_TOOL, output: unchanged(`desktop/${FRAME}.png`) },
      { name: "read_file", output: saved(`elsewhere/${FRAME}.png`) },
      { name: SCREENSHOT_TOOL, output: saved(`moved/desktop/${FRAME}.png`) },
    ]);
    expect([...found]).toEqual([
      [FRAME, `moved/desktop/${FRAME}.png`],
      [LATER, `${DEEP}/desktop/${LATER}.png`],
    ]);
  });
});

describe("a frame found in a conversation's messages", () => {
  const at = (minute: number) => `2026-10-14T01:${String(minute).padStart(2, "0")}:00+00:00`;
  const message = (minute: number, rest: Partial<StoredMessage>): StoredMessage => ({
    id: `m${minute}`,
    seq: minute,
    role: "tool",
    content: "",
    tool_calls: [],
    tool_call_id: null,
    name: null,
    provider: null,
    model: null,
    cost_usd: null,
    created_at: at(minute),
    ...rest,
  });
  const call = (id: string, name: string, minute: number) => message(minute, { role: "assistant", tool_calls: [{ id, name, arguments: {} }] });
  const answer = (id: string, content: string, minute: number, name: string | null = null) => message(minute, { content, tool_call_id: id, name });

  it("is the screenshot that saved it, matched to its call, with when", () => {
    const messages = [call("c1", SCREENSHOT_TOOL, 1), answer("c1", saved(`desktop/${FRAME}.png`), 2)];
    expect(savedInMessages(messages, FRAME)).toEqual({ path: `desktop/${FRAME}.png`, at: at(2) });
    expect(savedInMessages(messages, LATER)).toBeNull();
  });

  it("is the latest that saved it", () => {
    const messages = [
      call("c1", SCREENSHOT_TOOL, 1),
      answer("c1", saved(`desktop/${FRAME}.png`), 2),
      call("c2", SCREENSHOT_TOOL, 3),
      answer("c2", saved(`${DEEP}/desktop/${FRAME}.png`), 4),
    ];
    expect(savedInMessages(messages, FRAME)).toEqual({ path: `${DEEP}/desktop/${FRAME}.png`, at: at(4) });
  });

  it("is never the answer of another tool that reads the same", () => {
    const messages = [call("c1", "read_file", 1), answer("c1", saved(`desktop/${FRAME}.png`), 2, SCREENSHOT_TOOL)];
    expect(savedInMessages(messages, FRAME)).toBeNull();
  });

  it("falls back to the answer's own tool name when its call is not in reach", () => {
    const messages = [answer("gone", saved(`desktop/${FRAME}.png`), 2, SCREENSHOT_TOOL)];
    expect(savedInMessages(messages, FRAME)).toEqual({ path: `desktop/${FRAME}.png`, at: at(2) });
  });
});
