import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import { writeDraft } from "../../lib/canvas-draft";
import { landed, startServer, stopServer } from "../../test/canvas-hook";
import { historyShown } from "../../test/canvas-history";
import { editor, mode, openPanel, versionLine } from "../../test/canvas-panel";
import type { FakeBackend } from "../../test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
  vitest.setSystemTime(new Date("2026-10-02T03:05:00Z"));
});

afterEach(stopServer);

describe("the mode a canvas opens in", () => {
  it("is editing for a canvas just made here, even when an agent wrote to it before it was read", async () => {
    backend.canvas.add({ title: vi.canvas.untitled });
    backend.canvas.write("a1", "Ming viết trước\n", { author: "agent:ming" });

    await openPanel({ created: true });

    expect(mode()).toBe(vi.canvas.edit);
    expect(editor()?.value).toBe("Ming viết trước\n");
  });

  it("is editing for typing merged into an agent's newer version, which says so until it is saved", async () => {
    const base = "Dòng một\nDòng hai\nDòng ba\n";
    backend.canvas.add({ title: "Báo cáo", agent_id: "ming", content: base });
    backend.canvas.write("a1", "Dòng một\nDòng hai\nDòng ba của Ming\n", { author: "agent:ming" });
    writeDraft({ artifact_id: "a1", base_version: 1, base, text: "Dòng một của tôi\nDòng hai\nDòng ba\n", saved_at: Date.now(), sent: [] });

    await openPanel();

    expect(mode()).toBe(vi.canvas.edit);
    expect(editor()?.value).toBe("Dòng một của tôi\nDòng hai\nDòng ba của Ming\n");
    expect(screen.getByText(vi.canvas.merged)).toBeTruthy();
    fireEvent.keyDown(editor() as HTMLTextAreaElement, { key: "s", ctrlKey: true });
    await landed();
    expect(screen.queryByText(vi.canvas.merged)).toBeNull();
  });

  it("sets a person's code in the code face", async () => {
    backend.canvas.add({ title: "Mã", kind: "code", content: "print(1)\n" });

    await openPanel();

    expect(editor()).toHaveClass("canvas-editor", "code");
  });
});

describe("the canvas's header", () => {
  it("opens the name of a canvas just made here for editing, up to 200 characters", async () => {
    backend.canvas.add({ title: vi.canvas.untitled });

    await openPanel({ created: true });

    expect(screen.getByRole("textbox", { name: vi.canvas.rename })).toHaveAttribute("maxlength", "200");
  });

  it("shows no version line while the canvas is read, even when a newer version is announced", async () => {
    backend.canvas.add({ title: "Báo cáo", agent_id: "ming", content: "a" });
    backend.canvas.holdNext("GET /artifacts/a1", "request");
    await openPanel();

    act(() => {
      backend.canvas.write("a1", "b", { author: "agent:ming" });
    });
    await landed();

    expect(versionLine()).toBeNull();
  });

  it("closes the history when the person chooses how to show the canvas", async () => {
    backend.canvas.add({ title: "Ghi chú", content: "a" });
    await openPanel();
    fireEvent.click(screen.getByRole("button", { name: vi.canvas.history }));
    await landed();
    expect(historyShown()).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.view }));

    expect(historyShown()).toBe(false);
  });
});
