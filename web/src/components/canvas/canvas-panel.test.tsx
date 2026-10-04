import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import { writeDraft } from "../../lib/canvas-draft";
import { landed, startServer, stopServer } from "../../test/canvas-hook";
import { editor, mode, openPanel, typeInto, versionLine } from "../../test/canvas-panel";
import type { FakeBackend } from "../../test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
  vitest.setSystemTime(new Date("2026-10-02T03:05:00Z"));
});

afterEach(stopServer);

const title = () => screen.getByRole("heading", { level: 2 }).textContent;
const shown = (container: HTMLElement) => container.querySelector(".canvas-view") as HTMLElement;

/** Clicks the name `from`, types `to` in its place and presses Enter. */
async function rename(from: string, to: string) {
  fireEvent.click(screen.getByRole("button", { name: from }));
  const field = screen.getByRole("textbox", { name: vi.canvas.rename });
  fireEvent.change(field, { target: { value: to } });
  fireEvent.keyDown(field, { key: "Enter" });
  await landed();
}

describe("reading and editing", () => {
  it("opens a person's canvas to edit, and switches to reading and back without losing the typing", async () => {
    backend.canvas.add({ title: "Ghi chú", content: "# Kế hoạch\n\nBước một" });
    const { container } = await openPanel();
    expect(mode()).toBe(vi.canvas.edit);
    typeInto("# Kế hoạch\n\nBước một và hai");

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.view }));

    expect(editor()).toBeNull();
    expect(within(shown(container)).getByRole("heading", { level: 1 }).textContent).toBe("Kế hoạch");
    expect(within(shown(container)).getByText("Bước một và hai")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: vi.canvas.edit }));
    expect(editor()?.value).toBe("# Kế hoạch\n\nBước một và hai");
  });

  it("opens a canvas an agent wrote to read, and keeps reading when a newer version arrives", async () => {
    backend.canvas.add({ title: "Báo cáo", agent_id: "ming", content: "Bản của Ming" });
    const { container } = await openPanel();
    expect(mode()).toBe(vi.canvas.view);
    expect(versionLine()).toBe("v1 · Ming · 5 phút");

    act(() => {
      backend.canvas.write("a1", "Bản của tôi", { author: "user" });
    });
    await landed();

    expect(mode()).toBe(vi.canvas.view);
    expect(shown(container).textContent).toBe("Bản của tôi");
    expect(versionLine()).toBe("v2 · bạn · 4 phút");
  });

  it("keeps a person's canvas in editing when an agent writes to it", async () => {
    backend.canvas.add({ title: "Ghi chú", content: "a" });
    await openPanel();

    act(() => {
      backend.canvas.write("a1", "b", { author: "agent:ming" });
    });
    await landed();

    expect(mode()).toBe(vi.canvas.edit);
    expect(editor()?.value).toBe("b");
    expect(versionLine()).toBe("v2 · Ming · 4 phút");
  });

  it("opens a draft kept on this device to edit, even on a canvas an agent wrote", async () => {
    backend.canvas.add({ title: "Báo cáo", agent_id: "ming", content: "Bản của Ming" });
    const base = "Bản của Ming";
    writeDraft({ artifact_id: "a1", base_version: 1, base, text: "Bản của Ming, sửa dở", saved_at: Date.now(), sent: [] });

    await openPanel();

    expect(mode()).toBe(vi.canvas.edit);
    expect(editor()?.value).toBe("Bản của Ming, sửa dở");
    expect(screen.getByText(vi.canvas.draftOpened)).toBeTruthy();
  });

  it.each(["markdown", "code"] as const)("shows markup in a %s canvas as text", async (kind) => {
    const content = '<script>alert(1)</script>\n\n<img src="x" onerror="alert(2)">';
    backend.canvas.add({ kind, agent_id: "ming", content });

    const { container } = await openPanel();

    expect(shown(container).querySelector("script, img")).toBeNull();
    expect(shown(container).textContent).toContain("<script>alert(1)</script>");
    expect(shown(container).textContent).toContain('<img src="x" onerror="alert(2)">');
  });

  it.each([
    ["markdown", "a‮(trang-khac)\n\n```\na​b\n```", ["a[U+202E](trang-khac)", "a[U+200B]b"]],
    ["code", "x = 1‮\ny​", ["x = 1[U+202E]", "y[U+200B]"]],
  ] as const)("marks the hidden characters of a %s canvas and says it has them", async (kind, content, marks) => {
    backend.canvas.add({ kind, agent_id: "ming", content });

    const { container } = await openPanel();

    for (const mark of marks) expect(shown(container).textContent).toContain(mark);
    expect(within(shown(container)).queryByRole("link")).toBeNull();
    expect(screen.getByRole("note").textContent).toBe(`${vi.canvas.hiddenChars} ${vi.canvas.hiddenCharsHint}`);
  });
});

describe("the name", () => {
  it("renames the canvas with a PATCH and shows the new name", async () => {
    backend.canvas.add({ title: "Ghi chú", content: "a" });
    await openPanel();

    await rename("Ghi chú", "Kế hoạch");

    expect(backend.requests.filter((request) => request.method === "PATCH")).toEqual([
      { method: "PATCH", path: "/artifacts/a1", body: { title: "Kế hoạch" } },
    ]);
    expect(title()).toBe("Kế hoạch");
  });

  it("opens a canvas just made with its name ready to type over and its text to edit", async () => {
    backend.canvas.add({ title: "Tài liệu không tên" });

    await openPanel({ created: true });

    // `openPanel` lands inside act, so the effect that focuses the field has run; waitFor would
    // hang here, its last wait being a setTimeout these tests fake.
    const field = screen.getByRole("textbox", { name: vi.canvas.rename }) as HTMLInputElement;
    expect(document.activeElement).toBe(field);
    expect(field.value).toBe("Tài liệu không tên");
    expect(mode()).toBe(vi.canvas.edit);
  });

  it.each([
    [422, "Không đổi được tên: tên trống hoặc dài quá 200 ký tự"],
    [503, "Không đổi được tên: máy chủ không phản hồi"],
  ])("says why a rename refused with %i failed, until a rename lands", async (status, message) => {
    backend.canvas.add({ title: "Ghi chú", content: "a" });
    await openPanel();
    backend.canvas.refuseNext("PATCH", status);

    await rename("Ghi chú", "Kế hoạch");
    expect(screen.getByRole("alert").textContent).toBe(message);
    expect(title()).toBe("Ghi chú");

    await rename("Ghi chú", "Kế hoạch");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(title()).toBe("Kế hoạch");
  });

  it("takes a rename the server cannot find for the canvas's deletion", async () => {
    backend.canvas.add({ title: "Ghi chú", content: "a" });
    await openPanel();
    backend.canvas.refuseNext("PATCH", 404);

    await rename("Ghi chú", "Kế hoạch");

    expect(screen.getByRole("alert").textContent).toBe(`${vi.canvas.gone} ${vi.canvas.goneHint}`);
    expect(editor()?.readOnly).toBe(true);
  });
});

describe("a deleted canvas", () => {
  it("keeps its text to read and copy, and offers nothing that needs the canvas", async () => {
    backend.canvas.add({ title: "Ghi chú", content: "a" });
    const { handles } = await openPanel();

    act(() => backend.canvas.remove("a1"));

    expect(screen.getByRole("alert").textContent).toBe(`${vi.canvas.gone} ${vi.canvas.goneHint}`);
    expect(editor()).toMatchObject({ value: "a", readOnly: true });
    expect(title()).toBe("Ghi chú");
    expect(screen.queryByRole("button", { name: "Ghi chú" })).toBeNull();
    expect(screen.queryByRole("button", { name: vi.canvas.history })).toBeNull();
    expect(screen.queryByRole("link", { name: vi.canvas.download })).toBeNull();
    expect(screen.getByRole("button", { name: vi.canvas.copy })).toBeTruthy();
    expect(handles.at(-1)?.gone()).toBe(true);
  });
});

describe("where the canvas came from", () => {
  it("heads the body of a canvas read from a file, above its text, and stays there over the versions", async () => {
    backend.canvas.add({ title: "Thực đơn", content: "a", source: "workspace:ming/notes/thuc-don.md" });
    const { container } = await openPanel();
    const head = () => container.querySelector(".canvas-body")?.firstElementChild;

    expect(head()).toHaveClass("canvas-source");
    expect(head()?.textContent).toBe(`${vi.canvas.source.label}Ming/notes/thuc-don.md${vi.canvas.source.reimport}`);

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.history }));
    await landed();
    expect(screen.getByRole("region", { name: vi.canvas.historyTitle })).toBeTruthy();
    expect(head()).toHaveClass("canvas-source");
  });

  it("is not there for a canvas made here", async () => {
    backend.canvas.add({ title: "Ghi chú", content: "a" });
    const { container } = await openPanel();

    expect(editor()?.value).toBe("a");
    expect(container.querySelector(".canvas-source")).toBeNull();
    expect(screen.queryByRole("button", { name: vi.canvas.source.reimport })).toBeNull();
  });
});

describe("the header and the dock", () => {
  it("goes back to the list, closes, and downloads the newest version", async () => {
    backend.canvas.add({ title: "Ghi chú", content: "a" });
    const { props } = await openPanel();

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.toList }));
    fireEvent.click(screen.getByRole("button", { name: vi.canvas.close }));

    expect(props.onShowList).toHaveBeenCalledTimes(1);
    expect(props.onClose).toHaveBeenCalledTimes(1);
    const download = screen.getByRole("link", { name: vi.canvas.download });
    expect(download.getAttribute("href")).toBe("/api/artifacts/a1/raw?download=1");
  });

  it("copies the text as it is, unmarked", async () => {
    const writeText = vitest.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    backend.canvas.add({ title: "Ghi chú", agent_id: "ming", content: "x​y" });
    await openPanel();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: vi.canvas.copy }));
    });

    expect(writeText).toHaveBeenCalledWith("x​y");
    Reflect.deleteProperty(navigator, "clipboard");
  });

  it("lets the dock save the open text and ask whether the canvas is gone, and lets go when it unmounts", async () => {
    backend.canvas.add({ title: "Ghi chú", content: "a" });
    const { handles, unbind, unmount } = await openPanel();
    typeInto("ab");

    const version = await act(() => handles[0].flush());

    expect(version).toBe(2);
    expect(backend.canvas.content("a1")).toBe("ab");
    expect(handles).toHaveLength(1);
    expect(handles[0].gone()).toBe(false);
    unmount();
    expect(unbind).toHaveBeenCalledTimes(1);
  });
});
