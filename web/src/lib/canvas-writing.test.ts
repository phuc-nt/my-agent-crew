import { describe, expect, it, vi as vitest } from "vitest";
import type { WritingPreview } from "../state/writing-previews";
import { describeWriting } from "./canvas-writing";

const NOTE = "0123456789ab";

const preview = (text: string, partial: Partial<WritingPreview> = {}): WritingPreview => ({
  key: 4,
  index: 0,
  name: "artifact_create",
  text,
  attempt: 0,
  callId: null,
  updates: 2,
  ...partial,
});
const rewrite = (text: string, partial: Partial<WritingPreview> = {}) => preview(text, { name: "artifact_rewrite", ...partial });

/** A tab that knows one canvas, the note, and no other. */
const known = () => ({
  titleOf: vitest.fn((id: string) => (id === NOTE ? "Ghi chú" : null)),
  kindOf: vitest.fn((id: string) => (id === NOTE ? "markdown" : null)),
});
const nothing = { titleOf: () => null, kindOf: () => null };

describe("what a canvas being made is shown as", () => {
  it("carries the preview's key, call and count, and what its arguments say so far", () => {
    const item = describeWriting(preview('{"title":"Kế hoạch","kind":"markdown","content":"# Tuần\\n\\nViệc'), nothing);
    expect(item).toEqual({
      key: 4,
      callId: null,
      updates: 2,
      rewrite: false,
      id: null,
      title: "Kế hoạch",
      kind: "markdown",
      content: "# Tuần\n\nViệc",
      bytes: 16,
    });
    expect(describeWriting(preview("{", { callId: "w1", key: 9, updates: 5 }), nothing)).toMatchObject({
      key: 9,
      callId: "w1",
      updates: 5,
    });
  });

  it("has no title, no kind and no text before the arguments say any", () => {
    expect(describeWriting(preview('{"ti'), nothing)).toMatchObject({ title: null, kind: null, content: "", bytes: 0 });
    expect(describeWriting(preview(""), nothing)).toMatchObject({ title: null, kind: null, content: "", bytes: 0 });
  });

  it("counts the size as the bytes the text will take, not its characters", () => {
    expect(describeWriting(preview('{"content":"abc'), nothing).bytes).toBe(3);
    expect(describeWriting(preview('{"content":"Việc'), nothing).bytes).toBe(6);
    expect(describeWriting(preview('{"content":"vui \\ud83d\\ude00'), nothing).bytes).toBe(8);
  });

  it("shows the title as the server will keep it, without what cannot be seen in it", () => {
    const override = String.fromCharCode(0x202e);
    const title = `  Kế${override} hoạch\ttuần  `;
    const item = describeWriting(preview(JSON.stringify({ title })), nothing);
    expect(item.title).toBe("Kế hoạch tuần");
  });

  it("has no title when the one written cannot be kept: blank, or too long", () => {
    expect(describeWriting(preview(JSON.stringify({ title: " \t " })), nothing).title).toBeNull();
    expect(describeWriting(preview(JSON.stringify({ title: "a".repeat(201) })), nothing).title).toBeNull();
    expect(describeWriting(preview(JSON.stringify({ title: "a".repeat(200) })), nothing).title).toBe("a".repeat(200));
  });

  it("takes a kind only when it is one a canvas can be", () => {
    for (const kind of ["markdown", "code", "html", "svg", "mermaid"]) {
      expect(describeWriting(preview(JSON.stringify({ kind })), nothing).kind).toBe(kind);
    }
    for (const kind of ["pdf", "Markdown", "", " html", "constructor", "toString", "__proto__", "hasOwnProperty"]) {
      expect(describeWriting(preview(JSON.stringify({ kind })), nothing).kind).toBeNull();
    }
  });

  it("names no canvas, whatever id its arguments carry, and asks about none", () => {
    const lookup = known();
    const item = describeWriting(preview(JSON.stringify({ id: NOTE, title: "Mới", content: "x" })), lookup);
    expect(item).toMatchObject({ rewrite: false, id: null, title: "Mới", kind: null });
    expect(lookup.titleOf).not.toHaveBeenCalled();
    expect(lookup.kindOf).not.toHaveBeenCalled();
  });
});

describe("what a canvas being written again is shown as", () => {
  it("takes the title and the kind of the canvas it names, once the id is whole", () => {
    const item = describeWriting(rewrite(`{"id":"${NOTE}","content":"Bản mới`), known());
    expect(item).toMatchObject({ rewrite: true, id: NOTE, title: "Ghi chú", kind: "markdown", content: "Bản mới", bytes: 11 });
  });

  it("names no canvas while the id is still being written", () => {
    const lookup = known();
    const item = describeWriting(rewrite(`{"id":"${NOTE.slice(0, 11)}`), lookup);
    expect(item).toMatchObject({ rewrite: true, id: null, title: null, kind: null });
    expect(lookup.titleOf).not.toHaveBeenCalled();
  });

  it("names no canvas for an id the server could not have made, and asks about none", () => {
    for (const id of ["../../etc", "0123456789AB", "0123456789abc", `${NOTE}\n`, "", "a1"]) {
      const lookup = known();
      const item = describeWriting(rewrite(JSON.stringify({ id, content: "x" })), lookup);
      expect(item).toMatchObject({ id: null, title: null, kind: null, content: "x" });
      expect(lookup.titleOf).not.toHaveBeenCalled();
      expect(lookup.kindOf).not.toHaveBeenCalled();
    }
  });

  it("keeps the title the canvas has over the one the arguments give, and takes theirs for one it does not know", () => {
    const args = (id: string) => JSON.stringify({ id, title: "Tên trong lời gọi", content: "x" });
    expect(describeWriting(rewrite(args(NOTE)), known()).title).toBe("Ghi chú");
    expect(describeWriting(rewrite(args("ba9876543210")), known())).toMatchObject({
      id: "ba9876543210",
      title: "Tên trong lời gọi",
      kind: null,
    });
  });

  it("shows the title the arguments give until the id says which canvas it is", () => {
    const early = describeWriting(rewrite(`{"title":"Tên mới","id":"${NOTE.slice(0, 5)}`), known());
    expect(early).toMatchObject({ id: null, title: "Tên mới", kind: null });
    const whole = describeWriting(rewrite(`{"title":"Tên mới","id":"${NOTE}"`), known());
    expect(whole).toMatchObject({ id: NOTE, title: "Ghi chú", kind: "markdown" });
  });

  it("cleans the title the arguments give as it does for a canvas being made", () => {
    const item = describeWriting(rewrite(JSON.stringify({ id: "ba9876543210", title: "a".repeat(201) })), known());
    expect(item.title).toBeNull();
  });

  it("takes no kind from the arguments: the canvas has the one it was made with", () => {
    const item = describeWriting(rewrite(JSON.stringify({ id: "ba9876543210", kind: "html", content: "x" })), known());
    expect(item.kind).toBeNull();
  });

  it("takes a kind the tab was told only when it is one a canvas can be", () => {
    const odd = { titleOf: () => "Lạ", kindOf: () => "constructor" };
    expect(describeWriting(rewrite(JSON.stringify({ id: NOTE })), odd).kind).toBeNull();
    const image = { titleOf: () => "Ảnh", kindOf: () => "image" };
    expect(describeWriting(rewrite(JSON.stringify({ id: NOTE })), image).kind).toBe("image");
  });
});
