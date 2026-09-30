import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import { memoryStorage, refusingStorage } from "../test/memory-storage";
import { forgetDraft, saveDraft, useDraft } from "./use-draft";

afterEach(() => vitest.unstubAllGlobals());

function draft(key: string | null) {
  return renderHook(({ key }) => useDraft(key), { initialProps: { key } });
}

describe("the unsent text kept per conversation", () => {
  it("brings each conversation's own text back when it is shown again", () => {
    memoryStorage();
    const hook = draft("c1");
    act(() => hook.result.current[1]("xin chào, mai"));

    hook.rerender({ key: "c2" });
    expect(hook.result.current[0]).toBe("");
    act(() => hook.result.current[1]("việc khác"));

    hook.rerender({ key: "c1" });
    expect(hook.result.current[0]).toBe("xin chào, mai");
    hook.rerender({ key: "c2" });
    expect(hook.result.current[0]).toBe("việc khác");
  });

  it("survives a reload, and an emptied box leaves nothing behind", () => {
    const store = memoryStorage();
    const first = draft("c1");
    act(() => first.result.current[1]("nửa câu"));
    first.unmount();

    const again = draft("c1");
    expect(again.result.current[0]).toBe("nửa câu");

    // What the composer does once the message is sent.
    act(() => again.result.current[1](""));
    expect(again.result.current[0]).toBe("");
    expect(store.size).toBe(0);
  });

  it("keeps the text in memory only without a key", () => {
    const store = memoryStorage();
    const hook = draft(null);
    act(() => hook.result.current[1]("tạm"));
    expect(hook.result.current[0]).toBe("tạm");
    expect(store.size).toBe(0);
  });

  it("goes on typing where the browser refuses storage, and only forgets on switching", () => {
    refusingStorage();
    const hook = draft("c1");
    expect(hook.result.current[0]).toBe("");
    act(() => hook.result.current[1]("vẫn gõ được"));
    expect(hook.result.current[0]).toBe("vẫn gõ được");

    hook.rerender({ key: "c2" });
    expect(hook.result.current[0]).toBe("");
  });
});

describe("saveDraft: seeding a draft before its useDraft ever mounts", () => {
  it("is read back by useDraft once it mounts on that key", () => {
    memoryStorage();
    saveDraft("c-fork", "hỏi lại");
    const hook = draft("c-fork");
    expect(hook.result.current[0]).toBe("hỏi lại");
  });

  it("is picked up by a useDraft already mounted, the moment its key switches to it", () => {
    memoryStorage();
    const hook = draft("c1");
    saveDraft("c-fork", "chữ đã lưu trước");
    hook.rerender({ key: "c-fork" });
    expect(hook.result.current[0]).toBe("chữ đã lưu trước");
  });

  it("forgetDraft still empties what saveDraft wrote", () => {
    const store = memoryStorage();
    saveDraft("c-fork", "sẽ bị xoá");
    forgetDraft("c-fork");
    expect(draft("c-fork").result.current[0]).toBe("");
    expect(store.size).toBe(0);
  });
});
