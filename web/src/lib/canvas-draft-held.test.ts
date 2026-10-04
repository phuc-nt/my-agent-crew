import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { askedToStay } from "../test/close-page";
import { fullStorage, memoryStorage, refusingStorage } from "../test/memory-storage";
import { type CanvasDraft, dropFromTab, heldInTab, readDraft, writeDraft } from "./canvas-draft";

function draft(id: string, overrides: Partial<CanvasDraft> = {}): CanvasDraft {
  return { artifact_id: id, base_version: 3, base: "base", text: "base and more", saved_at: 0, sent: [], ...overrides };
}

let store: Map<string, string>;

beforeEach(() => {
  store = memoryStorage();
});

afterEach(() => {
  vitest.unstubAllGlobals();
  vitest.restoreAllMocks();
});

describe("whether a canvas's draft is held by this tab alone", () => {
  it("is so for the canvas whose draft the browser refused, and for no other", () => {
    refusingStorage();
    expect(writeDraft(draft("a1"))).toBe(false);

    expect(heldInTab("a1")).toBe(true);
    expect(heldInTab("a2")).toBe(false);
  });

  it("is not so for a draft the browser stored, nor where nothing was kept", () => {
    expect(heldInTab("a1")).toBe(false);

    expect(writeDraft(draft("a1"))).toBe(true);

    expect(readDraft("a1")).not.toBeNull();
    expect(heldInTab("a1")).toBe(false);
  });

  it("is no longer so once the browser keeps a later draft after all", () => {
    refusingStorage();
    writeDraft(draft("a1"));
    store = memoryStorage();

    writeDraft(draft("a1", { text: "base and much more" }));

    expect(heldInTab("a1")).toBe(false);
  });
});

describe("dropping the draft this tab holds", () => {
  it("drops it whatever its text, and the page no longer asks before it closes", () => {
    refusingStorage();
    writeDraft(draft("a1", { text: "words no save ever sent" }));
    expect(askedToStay()).toBe(true);

    dropFromTab("a1");

    expect(heldInTab("a1")).toBe(false);
    expect(readDraft("a1")).toBeNull();
    expect(askedToStay()).toBe(false);
  });

  it("leaves the page asking while this tab still holds another canvas's draft", () => {
    refusingStorage();
    writeDraft(draft("a1"));
    writeDraft(draft("a2"));

    dropFromTab("a1");

    expect(heldInTab("a2")).toBe(true);
    expect(askedToStay()).toBe(true);
  });

  it("leaves what another tab stored for the same canvas", () => {
    fullStorage(store);
    writeDraft(draft("a1", { text: "typed here" }));
    store.set("canvas-draft:a1", JSON.stringify(draft("a1", { text: "typed elsewhere" })));

    dropFromTab("a1");

    expect(readDraft("a1")?.text).toBe("typed elsewhere");
  });

  it("does nothing for a canvas this tab holds no draft of", () => {
    refusingStorage();
    writeDraft(draft("a1"));

    dropFromTab("a2");

    expect(heldInTab("a1")).toBe(true);
    expect(askedToStay()).toBe(true);
  });
});
