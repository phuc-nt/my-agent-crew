import { act, renderHook } from "@testing-library/react";
import { type ReactNode, useLayoutEffect } from "react";
import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import { memoryStorage, refusingStorage } from "../test/memory-storage";
import { forgetDraft, holdDraft, saveDraft, useDraft, withdrawDraft } from "./use-draft";

// The holds a test took: what holds a box lives with the module, so each is let go again.
const holds: (() => void)[] = [];

function hold(key: string): () => void {
  const release = holdDraft(key);
  holds.push(release);
  return release;
}

afterEach(() => {
  for (const release of holds.splice(0)) release();
  vitest.unstubAllGlobals();
});

function draft(key: string | null) {
  return renderHook(({ key }) => useDraft(key), { initialProps: { key } });
}

/** Takes the words back out of a conversation's box, and says whether they are taken. */
function withdraw(key: string, words: string): boolean {
  let taken = false;
  act(() => {
    taken = withdrawDraft(key, words);
  });
  return taken;
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

describe("withdrawDraft: words the page handed back, taken out of the box again", () => {
  it("empties the kept draft and the box on screen that hold those very words", () => {
    const store = memoryStorage();
    const hook = draft("c1");
    act(() => hook.result.current[1]("gửi đi"));

    expect(withdraw("c1", "gửi đi")).toBe(true);
    expect(hook.result.current[0]).toBe("");
    expect(store.size).toBe(0);
  });

  it("takes the words whatever space stands around them in the box", () => {
    const store = memoryStorage();
    const hook = draft("c1");
    act(() => hook.result.current[1]("  gửi đi\n"));

    expect(withdraw("c1", "gửi đi")).toBe(true);
    expect(hook.result.current[0]).toBe("");
    expect(store.size).toBe(0);
  });

  it("leaves a box the person changed, and still answers that the words are taken", () => {
    const store = memoryStorage();
    const hook = draft("c1");
    act(() => hook.result.current[1]("gửi đi nhé"));

    expect(withdraw("c1", "gửi đi")).toBe(true);
    expect(hook.result.current[0]).toBe("gửi đi nhé");
    expect(store.get("composer-draft:c1")).toBe("gửi đi nhé");
  });

  it("empties the draft of a conversation off screen, and leaves the box that is on it", () => {
    const store = memoryStorage();
    const hook = draft("c1");
    act(() => hook.result.current[1]("gửi đi"));
    hook.rerender({ key: "c2" });
    act(() => hook.result.current[1]("gửi đi"));

    expect(withdraw("c1", "gửi đi")).toBe(true);
    // The other conversation's own words, the same ones, are not what was handed back.
    expect(hook.result.current[0]).toBe("gửi đi");
    expect(store.get("composer-draft:c2")).toBe("gửi đi");
    expect(store.has("composer-draft:c1")).toBe(false);
    hook.rerender({ key: "c1" });
    expect(hook.result.current[0]).toBe("");
  });

  it("empties the box on screen where the browser refuses storage", () => {
    refusingStorage();
    const hook = draft("c1");
    act(() => hook.result.current[1]("gửi đi"));

    expect(withdraw("c1", "gửi đi")).toBe(true);
    expect(hook.result.current[0]).toBe("");
  });

  it("empties a box that comes on screen in the very commit its words are taken back in", () => {
    const store = memoryStorage();
    saveDraft("c1", "gửi đi");
    // What takes the words back stands above the box, and does so as the box first shows.
    const wrapper = ({ children }: { children: ReactNode }) => {
      useLayoutEffect(() => {
        withdrawDraft("c1", "gửi đi");
      }, []);
      return children;
    };
    const hook = renderHook(() => useDraft("c1"), { wrapper });

    expect(hook.result.current[0]).toBe("");
    expect(store.size).toBe(0);
  });

  it("answers that the words are taken where there was no draft at all", () => {
    const store = memoryStorage();
    expect(withdraw("c1", "gửi đi")).toBe(true);
    expect(store.size).toBe(0);
  });
});

describe("holdDraft: a box whose words a send is carrying", () => {
  it("is not the page's to empty until the send lets go", () => {
    const store = memoryStorage();
    const hook = draft("c1");
    act(() => hook.result.current[1]("gửi đi"));
    const release = hold("c1");

    expect(withdraw("c1", "gửi đi")).toBe(false);
    expect(hook.result.current[0]).toBe("gửi đi");
    expect(store.get("composer-draft:c1")).toBe("gửi đi");

    release();
    expect(withdraw("c1", "gửi đi")).toBe(true);
    expect(hook.result.current[0]).toBe("");
    expect(store.size).toBe(0);
  });

  it("stays held until every send that holds it has let go", () => {
    memoryStorage();
    const first = hold("c1");
    const second = hold("c1");

    first();
    expect(withdraw("c1", "gửi đi")).toBe(false);
    second();
    expect(withdraw("c1", "gửi đi")).toBe(true);
  });

  it("is let go once by a send that lets go twice", () => {
    memoryStorage();
    const first = hold("c1");
    const second = hold("c1");

    first();
    first();
    expect(withdraw("c1", "gửi đi")).toBe(false);
    second();
    expect(withdraw("c1", "gửi đi")).toBe(true);
  });

  it("holds the box of its own conversation only", () => {
    const store = memoryStorage();
    saveDraft("c2", "gửi đi");
    hold("c1");

    expect(withdraw("c2", "gửi đi")).toBe(true);
    expect(store.size).toBe(0);
    expect(withdraw("c1", "gửi đi")).toBe(false);
  });
});
