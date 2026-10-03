import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { PanelHandle } from "../../hooks/use-canvas-dock";
import { vi } from "../../i18n/vi";
import { landed, startServer, stopServer } from "../../test/canvas-hook";
import { editor, mode, openPanel, typeInto } from "../../test/canvas-panel";
import type { FakeBackend } from "../../test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
});

afterEach(stopServer);

/** Whether the newest handle the panel lent the dock says its person is typing. */
const typing = (handles: PanelHandle[]) => handles.at(-1)?.typing();

describe("whether the person is typing in the panel", () => {
  it("is no for a canvas just opened, though its editor is there", async () => {
    backend.canvas.add({ title: "Ghi chú", content: "Bước một" });

    const { handles } = await openPanel();

    expect(editor()).not.toBeNull();
    expect(typing(handles)).toBe(false);
  });

  it("is yes while the text holds typing no save has taken, and no once one has", async () => {
    backend.canvas.add({ title: "Ghi chú", content: "Bước một" });
    const { handles } = await openPanel();

    typeInto("Bước một và hai");
    expect(typing(handles)).toBe(true);
    await act(() => handles.at(-1)?.flush() ?? Promise.resolve(null));
    await landed();

    expect(typing(handles)).toBe(false);
  });

  it("is yes while the editor holds the keyboard, saved or not, and no after it lets go", async () => {
    backend.canvas.add({ title: "Ghi chú", content: "Bước một" });
    const { handles } = await openPanel();

    act(() => editor()?.focus());
    expect(typing(handles)).toBe(true);
    act(() => editor()?.blur());
    await landed();

    expect(typing(handles)).toBe(false);
  });

  it("is no while the keyboard is on something else in the panel", async () => {
    backend.canvas.add({ title: "Ghi chú", content: "Bước một" });
    const { handles } = await openPanel();

    act(() => screen.getByRole("button", { name: vi.canvas.view }).focus());

    expect(document.activeElement).not.toBe(editor());
    expect(typing(handles)).toBe(false);
  });

  it("is no for a canvas being read, which has no field to type in", async () => {
    backend.canvas.add({ title: "Báo cáo", agent_id: "ming", content: "Bản của Ming" });

    const { handles } = await openPanel();

    expect(mode()).toBe(vi.canvas.view);
    expect(editor()).toBeNull();
    expect(typing(handles)).toBe(false);
  });

  it("stays yes in reading mode for typing no save has taken yet", async () => {
    backend.canvas.add({ title: "Ghi chú", content: "Bước một" });
    const { handles } = await openPanel();
    typeInto("Bước một và hai");

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.view }));

    expect(editor()).toBeNull();
    expect(typing(handles)).toBe(true);
  });

  it("is no again once the editor goes away holding nothing unsaved", async () => {
    backend.canvas.add({ title: "Ghi chú", content: "Bước một" });
    const { handles } = await openPanel();
    act(() => editor()?.focus());
    expect(typing(handles)).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.view }));
    await landed();

    expect(editor()).toBeNull();
    expect(typing(handles)).toBe(false);
  });

  it("is asked of the panel afresh, through one handle for as long as the panel stays", async () => {
    backend.canvas.add({ title: "Ghi chú", content: "Bước một" });
    const { handles } = await openPanel();

    typeInto("Bước một và hai");
    act(() => editor()?.focus());
    await act(() => handles.at(-1)?.flush() ?? Promise.resolve(null));
    await landed();

    expect(handles).toHaveLength(1);
  });
});
