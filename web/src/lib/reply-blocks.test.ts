import { describe, expect, it } from "vitest";
import { splitMedia } from "./reply-blocks";

const PLAN = "00ff00ff00ff";
const NOTE = "0123456789ab";

describe("splitMedia", () => {
  it("separates MEDIA: lines from text and keeps ordinary lines together", () => {
    expect(splitMedia("Đây là ảnh:\nMEDIA: out/chart.png\nxong")).toEqual([
      { kind: "text", value: "Đây là ảnh:" },
      { kind: "media", value: "out/chart.png" },
      { kind: "text", value: "xong" },
    ]);
    expect(splitMedia("MEDIA:")).toEqual([{ kind: "text", value: "MEDIA:" }]);
  });

  it("keeps the order the reply named its attachments in", () => {
    expect(splitMedia("a\nFILE: one.pdf\nb\nMEDIA: two.png\nc")).toEqual([
      { kind: "text", value: "a" },
      { kind: "file", value: "one.pdf" },
      { kind: "text", value: "b" },
      { kind: "media", value: "two.png" },
      { kind: "text", value: "c" },
    ]);
  });

  it("leaves a sentence that merely mentions the word as prose", () => {
    // Only a line that starts with the prefix is an attachment, so an agent explaining
    // the convention does not accidentally link to nothing.
    const text = "Dùng FILE: ở đầu dòng để gửi tệp";
    expect(splitMedia(`Mẹo: ${text}`)).toEqual([{ kind: "text", value: `Mẹo: ${text}` }]);
  });

  it("leaves a bare prefix with no path as prose", () => {
    // Otherwise it would become a download link aimed at the workspace root.
    expect(splitMedia("FILE:")).toEqual([{ kind: "text", value: "FILE:" }]);
  });

  it("reads a line that sends a canvas as that canvas, under either prefix, and keeps the line as written", () => {
    expect(splitMedia(`a\n  FILE: artifact:${PLAN}\nb\nMEDIA:artifact: ${NOTE} \nc`)).toEqual([
      { kind: "text", value: "a" },
      { kind: "canvas", id: PLAN, line: `FILE: artifact:${PLAN}` },
      { kind: "text", value: "b" },
      { kind: "canvas", id: NOTE, line: `MEDIA:artifact: ${NOTE}` },
      { kind: "text", value: "c" },
    ]);
  });

  it("still reads a line that sends a file of the workspace as the file, a canvas named inside its path too", () => {
    expect(splitMedia(`FILE: a.csv\nFILE: notes/artifact:${PLAN}\nMEDIA: Artifact:${PLAN}`)).toEqual([
      { kind: "file", value: "a.csv" },
      { kind: "file", value: `notes/artifact:${PLAN}` },
      { kind: "media", value: `Artifact:${PLAN}` },
    ]);
  });

  it("reads a line that sets out to name a canvas and names none as a canvas with no id, not as a file", () => {
    expect(splitMedia("FILE: artifact:xyz\nMEDIA: artifact:")).toEqual([
      { kind: "canvas", id: "", line: "FILE: artifact:xyz" },
      { kind: "canvas", id: "", line: "MEDIA: artifact:" },
    ]);
  });
});
