import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import type { ThreadItem } from "../../state/thread-reducer";
import { CanvasCard, type CanvasLinks, isCanvasWrite } from "./canvas-card";

const NOTE = "0123456789ab";
const card = vi.canvas.card;

type Tool = Extract<ThreadItem, { kind: "tool" }>;

function imported(fields: Partial<Tool> = {}): Tool {
  return { kind: "tool", id: "t1", name: "artifact_import", arguments: {}, output: null, status: "done", ...fields };
}

const tag = (version: number, unchanged = false) => `[artifact ${NOTE} v${version}${unchanged ? " unchanged" : ""}]\nImported.`;

function links(titles: Record<string, string> = {}) {
  return {
    titleOf: vitest.fn((id: string) => titles[id] ?? null),
    isGone: vitest.fn(() => false),
    verify: vitest.fn(),
    open: vitest.fn(),
  } satisfies CanvasLinks;
}

const shown = (item: Tool, canvas: CanvasLinks = links({ [NOTE]: "Thực đơn" })) => render(<CanvasCard item={item} canvas={canvas} />);
const root = () => screen.getByTestId("canvas-card");
const title = () => root().querySelector(".canvas-card-title")?.textContent;
const line = () => root().querySelector(".canvas-card-line")?.textContent;

describe("a file read into a canvas, in the thread", () => {
  it("is a canvas card while it runs and once it is done, and the plain tool card otherwise", () => {
    expect(isCanvasWrite(imported({ status: "running" }))).toBe(true);
    expect(isCanvasWrite(imported())).toBe(true);
    for (const status of ["failed", "denied", "stopped", "awaiting"] as const) {
      expect(isCanvasWrite(imported({ status })), status).toBe(false);
    }
  });

  it("says the file is being read while it runs, not that a canvas is being written", () => {
    shown(imported({ status: "running", arguments: { path: "thuc-don.md" } }));

    expect(line()).toBe(card.importing);
    expect(line()).toBe("Đang nhập…");
    expect(root().querySelector(".canvas-card-line svg")).not.toBeNull();
  });

  it("says a file was read into a new canvas when the call names none", () => {
    shown(imported({ arguments: { path: "thuc-don.md" }, output: tag(1) }));

    expect(line()).toBe(card.version(card.imported, 1));
    expect(line()).toBe("Đã nhập · v1");
  });

  it("says a file was read again when the call names the canvas to read it into", () => {
    shown(imported({ arguments: { path: "thuc-don.md", id: NOTE, replace: true }, output: tag(4) }));

    expect(line()).toBe(card.version(card.reimported, 4));
    expect(line()).toBe("Đã nhập lại · v4");
  });

  it("takes an id sent blank as the server reads a blank, or as anything but text, as none", () => {
    for (const id of ["", "   ", "\u{1F}", "\u{85}", null, 7]) {
      const view = shown(imported({ arguments: { path: "thuc-don.md", id }, output: tag(1) }));
      expect(line(), JSON.stringify(id)).toBe(card.version(card.imported, 1));
      view.unmount();
    }
  });

  it("says the file held what the canvas does, whether or not the call named the canvas", () => {
    const named = shown(imported({ arguments: { path: "thuc-don.md", id: NOTE }, output: tag(3, true) }));
    expect(line()).toBe("Không đổi · v3");
    named.unmount();

    shown(imported({ arguments: { path: "thuc-don.md" }, output: tag(1, true) }));
    expect(line()).toBe("Không đổi · v1");
  });

  it("says what was done without a version when the result carries no tag", () => {
    shown(imported({ arguments: { path: "thuc-don.md", id: NOTE }, output: "ok" }));

    expect(line()).toBe(card.reimported);
  });

  it("opens the canvas its tag names", () => {
    const canvas = links({ [NOTE]: "Thực đơn" });
    shown(imported({ arguments: { path: "thuc-don.md" }, output: tag(1) }), canvas);

    fireEvent.click(screen.getByRole("button", { name: card.openLabel("Thực đơn") }));

    expect(canvas.open).toHaveBeenCalledExactlyOnceWith(NOTE);
    expect(canvas.verify).toHaveBeenCalledExactlyOnceWith(NOTE);
  });
});

describe("the title of a file being read into a canvas", () => {
  it("is the title the call gives, cleaned as the server cleans one", () => {
    shown(imported({ status: "running", arguments: { path: "notes/thuc-don.md", title: "  Thực đơn\ntuần này " } }));

    expect(title()).toBe("Thực đơn tuần này");
  });

  it("is the name of the file when the call gives no title, or one the server would refuse", () => {
    for (const given of [undefined, "", "  \n ", 5, null]) {
      const view = shown(imported({ status: "running", arguments: { path: "notes/tuần 1/thuc-don.md", title: given } }));
      expect(title(), JSON.stringify(given)).toBe("thuc-don.md");
      view.unmount();
    }
  });

  it("shows a character that hides or reorders text in the name of the file as a mark", () => {
    shown(imported({ status: "running", arguments: { path: "notes/a\u{202E}b.md" } }));

    expect(title()).toBe("a[U+202E]b.md");
  });

  it("shows what the server stores of a name and nobody would see as marks", () => {
    const names: [string, string][] = [
      ["notes/plan.md ", "plan.md[U+0020]"],
      ["notes/ plan.md", "[U+0020]plan.md"],
      ["notes/pl\u{034F}an.md", "pl[U+034F]an.md"],
      ["notes/plan\u{FE0F}.md", "plan[U+FE0F].md"],
      ["notes/plan.md\u{3164}", "plan.md[U+3164]"],
      ["notes/\u{3164}", "[U+3164]"],
      ["notes/\u{A0}", "[U+00A0]"],
      ["notes/ ", "[U+0020]"],
      ["notes/\u{E000} 9.41\u{202F}AM.png", "[U+E000] 9.41[U+202F]AM.png"],
    ];
    for (const [path, name] of names) {
      const view = shown(imported({ status: "running", arguments: { path } }));
      expect(title(), JSON.stringify(path)).toBe(name);
      view.unmount();
    }
  });

  it("keeps the spaces inside a title the call gives, which the server keeps as one line", () => {
    shown(imported({ status: "running", arguments: { path: "notes/a.md ", title: " Thực đơn \u{A0} tuần " } }));

    expect(title()).toBe("Thực đơn tuần");
  });

  it("is only called a canvas when the call names no file either", () => {
    for (const path of [undefined, "", "///", 7]) {
      const view = shown(imported({ status: "running", arguments: { path } }));
      expect(title(), JSON.stringify(path)).toBe(card.untitled);
      view.unmount();
    }
  });

  it("is the title of the canvas the call names, which the thread knows, before the call's own", () => {
    const canvas = links({ [NOTE]: "Thực đơn" });
    shown(imported({ status: "running", arguments: { path: "notes/moi.md", id: NOTE, title: "Tên khác" } }), canvas);

    expect(title()).toBe("Thực đơn");
    expect(canvas.verify).not.toHaveBeenCalled();
  });

  it("is the title the thread knows the canvas by once it is done, never the name of the file", () => {
    shown(imported({ arguments: { path: "notes/thuc-don.md", title: "Tên trong đối số" }, output: tag(1) }), links());

    expect(title()).toBe(card.untitled);
  });

  it("is never the name of a file for a create, which reads none", () => {
    const create = { ...imported({ status: "running", arguments: { path: "notes/thuc-don.md" } }), name: "artifact_create" };
    shown(create);

    expect(title()).toBe(card.untitled);
    expect(line()).toBe(card.writing);
  });
});
