import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { ArtifactSummary } from "../../api/artifact-types";
import type { CanvasList } from "../../hooks/use-canvas-list";
import { vi } from "../../i18n/vi";
import { CanvasPicker } from "./canvas-picker";

beforeEach(() => {
  vitest.useFakeTimers({ toFake: ["Date"] });
  vitest.setSystemTime(new Date("2026-10-02T03:05:00Z"));
});

afterEach(() => {
  vitest.useRealTimers();
});

const summary = (overrides: Partial<ArtifactSummary>): ArtifactSummary => ({
  id: "a1",
  title: "Kế hoạch",
  kind: "markdown",
  language: "",
  agent_id: "",
  head_version: 1,
  source: "web",
  created_at: "2026-10-02T03:00:00+00:00",
  updated_at: "2026-10-02T03:00:00+00:00",
  ...overrides,
});

function picker(list: Partial<CanvasList>, flags: { creating?: boolean; createFailed?: boolean } = {}) {
  const retry = vitest.fn();
  const onOpen = vitest.fn();
  const onCreate = vitest.fn();
  render(
    <CanvasPicker
      list={{ items: null, failed: false, retry, ...list }}
      creating={flags.creating ?? false}
      createFailed={flags.createFailed ?? false}
      onOpen={onOpen}
      onCreate={onCreate}
    />,
  );
  return { retry, onOpen, onCreate };
}

describe("the canvases of a conversation", () => {
  it("says the list is loading until the first read lands", () => {
    picker({ items: null });

    expect(screen.getByText(vi.canvas.listLoading)).toBeTruthy();
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("says when the conversation has no canvas yet", () => {
    picker({ items: [] });

    expect(screen.getByText(vi.canvas.listEmpty)).toBeTruthy();
    expect(screen.queryByText(vi.canvas.listLoading)).toBeNull();
  });

  it("says the list could not be read, and reads it again on retry", () => {
    const { retry } = picker({ items: null, failed: true });

    expect(screen.getByRole("alert").textContent).toContain(vi.canvas.listFailed);
    expect(screen.queryByText(vi.canvas.listLoading)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: vi.canvas.retry }));

    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("keeps the canvases it has when reading them again fails", () => {
    picker({ items: [summary({})], failed: true });

    expect(screen.getByRole("alert").textContent).toContain(vi.canvas.listFailed);
    expect(screen.getByRole("button", { name: /Kế hoạch/ })).toBeTruthy();
  });

  it("shows each canvas with its kind, version and last change, and opens the one picked", () => {
    const { onOpen } = picker({
      items: [
        summary({ id: "a2", title: "", kind: "code", head_version: 4 }),
        summary({ id: "a1", title: "Kế hoạch", head_version: 3 }),
        summary({ id: "a3", title: "Trang", kind: "html", updated_at: "2026-10-02T03:04:30+00:00" }),
      ],
    });

    const rows = screen.getAllByRole("listitem").map((row) => row.textContent);
    expect(rows).toEqual([
      `${vi.canvas.untitled}Mã · v4 · 5 phút`,
      "Kế hoạchMarkdown · v3 · 5 phút",
      "TrangHTML · v1 · vừa xong",
    ]);
    fireEvent.click(screen.getByRole("button", { name: /Kế hoạch/ }));

    expect(onOpen).toHaveBeenCalledWith("a1");
  });

  it("names the kind of a drawing, a diagram and a picture, and an unknown kind as it is", () => {
    const at = "2026-10-02T03:04:30+00:00";
    picker({
      items: [
        summary({ id: "b1", title: "Hình", kind: "svg", updated_at: at }),
        summary({ id: "b2", title: "Sơ đồ", kind: "mermaid", updated_at: at }),
        summary({ id: "b3", title: "Ảnh chụp", kind: "image", updated_at: at }),
        summary({ id: "b4", title: "Tệp", kind: "pdf", updated_at: at }),
      ],
    });

    expect(screen.getAllByRole("listitem").map((row) => row.textContent)).toEqual([
      "HìnhSVG · v1 · vừa xong",
      "Sơ đồMermaid · v1 · vừa xong",
      "Ảnh chụpẢnh · v1 · vừa xong",
      "Tệppdf · v1 · vừa xong",
    ]);
  });

  it("makes a canvas, one at a time, and says when one could not be made", () => {
    const { onCreate } = picker({ items: [] });
    fireEvent.click(screen.getByRole("button", { name: vi.canvas.newCanvas }));
    expect(onCreate).toHaveBeenCalledTimes(1);
    expect(onCreate).toHaveBeenCalledWith("markdown");
    expect(screen.queryByRole("alert")).toBeNull();

    picker({ items: [] }, { creating: true, createFailed: true });

    const buttons = screen.getAllByRole("button", { name: vi.canvas.newCanvas }) as HTMLButtonElement[];
    expect(buttons.map((button) => button.disabled)).toEqual([false, true]);
    expect(screen.getByRole("alert").textContent).toBe(vi.canvas.createFailed);
  });

  it("offers the five kinds a person can make, never an image, and makes the one chosen", () => {
    const { onCreate } = picker({ items: [] });
    const select = screen.getByRole("combobox", { name: vi.canvas.kindLabel }) as HTMLSelectElement;

    expect(Array.from(select.options).map((option) => [option.value, option.textContent])).toEqual([
      ["markdown", "Markdown"],
      ["code", "Mã"],
      ["html", "HTML"],
      ["svg", "SVG"],
      ["mermaid", "Mermaid"],
    ]);
    expect(select.value).toBe("markdown");

    fireEvent.change(select, { target: { value: "html" } });
    fireEvent.click(screen.getByRole("button", { name: vi.canvas.newCanvas }));

    expect(onCreate).toHaveBeenCalledTimes(1);
    expect(onCreate).toHaveBeenCalledWith("html");
  });

  it("keeps the kind chosen for the next canvas, and changes it on the next choice", () => {
    const { onCreate } = picker({ items: [] });
    const select = screen.getByRole("combobox", { name: vi.canvas.kindLabel });
    const make = screen.getByRole("button", { name: vi.canvas.newCanvas });

    fireEvent.change(select, { target: { value: "mermaid" } });
    fireEvent.click(make);
    fireEvent.click(make);
    fireEvent.change(select, { target: { value: "svg" } });
    fireEvent.click(make);

    expect(onCreate.mock.calls).toEqual([["mermaid"], ["mermaid"], ["svg"]]);
  });

  it("holds the kind still while a canvas is being made", () => {
    picker({ items: [] }, { creating: true });

    expect((screen.getByRole("combobox", { name: vi.canvas.kindLabel }) as HTMLSelectElement).disabled).toBe(true);
  });
});
