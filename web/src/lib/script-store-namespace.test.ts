import { describe, expect, it } from "vitest";
import type { ScriptStoreNamespace } from "../api/script-store";
import { parseRoute } from "../hooks/use-route";
import { vi } from "../i18n/vi";
import { namespaceFill, namespaceWords } from "./script-store-namespace";

const { scriptStore: words } = vi;

const held = (overrides: Partial<ScriptStoreNamespace>): ScriptStoreNamespace => ({
  namespace: "job:brief",
  chars: 10,
  entries: [],
  ...overrides,
});

describe("what a namespace is called", () => {
  it("is a schedule by its name, with a way to its row among the jobs", () => {
    const said = namespaceWords("coach", held({ kind: "job", ref: "brief", title: "Bản tin sáng", orphan: false }));

    expect(said).toMatchObject({ kind: words.kinds.job, name: "Bản tin sáng", phrase: 'lịch "Bản tin sáng"', orphan: false });
    // A job's row is named by its agent and its schedule.
    expect(parseRoute(said.href as string)).toEqual({ kind: "manage", section: "jobs", param: "coach/brief" });
  });

  it("is a conversation by its title, with a way to the conversation", () => {
    const said = namespaceWords("coach", held({ namespace: "conv:1d2405e5c98d", kind: "conv", ref: "1d2405e5c98d", title: "Đơn mới", orphan: false }));

    expect(said).toMatchObject({ kind: words.kinds.conv, name: "Đơn mới", phrase: 'cuộc trò chuyện "Đơn mới"' });
    expect(parseRoute(said.href as string)).toEqual({ kind: "chat", conversationId: "1d2405e5c98d" });
  });

  it.each([null, "", "   ", undefined])("goes by its id when it has no title (%j)", (title) => {
    const said = namespaceWords("coach", held({ namespace: "conv:abc", kind: "conv", ref: "abc", title, orphan: false }));

    expect(said.name).toBe("abc");
    expect(said.phrase).toBe('cuộc trò chuyện "abc"');
    expect(said.href).toBe("#/chat/abc");
  });

  it("has no way to an owner that is gone, and says which kind of owner that was", () => {
    const job = namespaceWords("coach", held({ kind: "job", ref: "brief", title: null, orphan: true }));
    const conv = namespaceWords("coach", held({ namespace: "conv:abc", kind: "conv", ref: "abc", title: null, orphan: true }));

    expect(job).toMatchObject({ name: "brief", href: null, orphan: true, orphanHint: words.orphanHint.job });
    expect(conv).toMatchObject({ name: "abc", href: null, orphan: true, orphanHint: words.orphanHint.conv });
  });

  it("is its stored name alone when it is neither a schedule's nor a conversation's", () => {
    const said = namespaceWords("coach", held({ namespace: "misc", kind: "other", ref: "misc", title: null, orphan: false }));

    expect(said).toEqual({ kind: words.kinds.other, name: "misc", phrase: '"misc"', href: null, orphan: false, orphanHint: words.orphanHint.other });
  });

  // A server newer than this page may name a kind it has not heard of.
  it("treats a kind it does not know as neither", () => {
    const said = namespaceWords("coach", held({ namespace: "team:x", kind: "team" as never, ref: "x", title: "Đội", orphan: false }));

    expect(said).toMatchObject({ kind: words.kinds.other, name: "team:x", href: null });
  });

  it("is its stored name, with no word for its kind, from a server that sends nothing more", () => {
    const said = namespaceWords("coach", held({ namespace: "job:brief" }));

    expect(said).toMatchObject({ kind: null, name: "job:brief", phrase: '"job:brief"', href: null, orphan: false });
  });

  it("is given no way anywhere without the id the way is built from", () => {
    expect(namespaceWords("coach", held({ kind: "job", title: "Bản tin sáng", orphan: false })).href).toBeNull();
    expect(namespaceWords("coach", held({ kind: "job", ref: "", title: "Bản tin sáng", orphan: false })).href).toBeNull();
  });

  it("writes out a character nobody would see in a name, and keeps the id whole in the address", () => {
    const said = namespaceWords("coach", held({ namespace: "job:a\u202Eb", kind: "job", ref: "a\u202Eb", title: "Tin\u200B sáng", orphan: false }));

    expect(said.name).toBe("Tin[U+200B] sáng");
    expect(parseRoute(said.href as string)).toEqual({ kind: "manage", section: "jobs", param: "coach/a\u202Eb" });
    expect(namespaceWords("coach", held({ namespace: "job:a\u202Eb" })).name).toBe("job:a[U+202E]b");
  });
});

describe("how a sentence names a namespace", () => {
  it("has a title's quote and line break escaped, in the heading as in the sentence", () => {
    const said = namespaceWords("coach", held({ kind: "job", ref: "brief", title: 'Tin "sáng"\nXoá cả kho?', orphan: false }));

    expect(said.phrase).toBe('lịch "Tin \\"sáng\\"\\nXoá cả kho?"');
    expect(said.name).toBe('Tin \\"sáng\\"\\nXoá cả kho?');
  });

  it("leaves out the spaces a title opens and ends with, so the quotes close on its words", () => {
    const said = namespaceWords("coach", held({ namespace: "conv:abc", kind: "conv", ref: "abc", title: "  Đơn mới   ", orphan: false }));

    expect(said.phrase).toBe('cuộc trò chuyện "Đơn mới"');
    expect(said.name).toBe("Đơn mới");
  });

  it("cuts a title at eighty characters, and keeps it whole in the heading", () => {
    const said = namespaceWords("coach", held({ kind: "job", ref: "brief", title: "t".repeat(300), orphan: false }));

    expect(said.phrase).toBe(`lịch "${"t".repeat(80)}…"`);
    expect(said.name).toBe("t".repeat(300));
  });

  it("puts a stored name between quotes with the spaces it ends with written out, as the heading has it", () => {
    const said = namespaceWords("coach", held({ namespace: "kho\ncũ  ", kind: "other", ref: "kho\ncũ  ", title: null, orphan: false }));

    expect(said.phrase).toBe('"kho\\ncũ[U+0020][U+0020]"');
    expect(said.name).toBe("kho\\ncũ[U+0020][U+0020]");
  });

  it("writes out a character nobody would see, in the phrase as in the name", () => {
    const said = namespaceWords("coach", held({ kind: "job", ref: "brief", title: "Tin\u202E sáng", orphan: false }));

    expect(said.phrase).toBe('lịch "Tin[U+202E] sáng"');
    expect(namespaceWords("coach", held({ namespace: "job:a\u200Bb" })).phrase).toBe('"job:a[U+200B]b"');
  });
});

describe("how full a namespace is", () => {
  it("is its keys and values over the most one holds", () => {
    expect(namespaceFill(1000, 4000)).toEqual({ ratio: 0.25, state: "room" });
  });

  it("is near the limit from four fifths of it, and full at it", () => {
    expect(namespaceFill(7999, 10_000)?.state).toBe("room");
    expect(namespaceFill(8000, 10_000)?.state).toBe("near");
    expect(namespaceFill(9999, 10_000)?.state).toBe("near");
    expect(namespaceFill(10_000, 10_000)?.state).toBe("full");
    expect(namespaceFill(12_000, 10_000)?.state).toBe("full");
  });

  it.each([undefined, 0, -1, Number.NaN])("is not measured against a limit of %j", (limit) => {
    expect(namespaceFill(1000, limit)).toBeNull();
  });
});
