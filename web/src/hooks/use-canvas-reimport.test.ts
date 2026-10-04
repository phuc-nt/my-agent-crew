import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import { useCanvasReimport } from "./use-canvas-reimport";

afterEach(() => vitest.unstubAllGlobals());

/** The hook on a canvas that has heard of no version, with a flush that settles on `flushed`. */
function mount(flushed: number | null) {
  const canvas = { state: { seen: 0 }, imported: vitest.fn(), reload: vitest.fn() };
  const view = renderHook(() => useCanvasReimport("a1", canvas, async () => flushed));
  return { canvas, view };
}

describe("a re-import asked with no version to ask it on", () => {
  it("sends nothing and says the text is not saved, whether the flush names none or one below the first", async () => {
    const fetch = vitest.fn<typeof globalThis.fetch>();
    vitest.stubGlobal("fetch", fetch);

    for (const flushed of [null, 0, -1]) {
      const { canvas, view } = mount(flushed);

      await act(() => view.result.current.reimport());

      expect(view.result.current.note, String(flushed)).toEqual({
        tone: "error",
        text: "Chưa lưu được bản đang sửa nên chưa nhập lại.",
      });
      expect(view.result.current.busy, String(flushed)).toBe(false);
      expect(canvas.imported, String(flushed)).not.toHaveBeenCalled();
      view.unmount();
    }
    expect(fetch).not.toHaveBeenCalled();
  });

  it("asks on the first version, which is one", async () => {
    const summary = { id: "a1", head_version: 1 };
    const fetch = vitest.fn<typeof globalThis.fetch>(async () => Response.json({ changed: false, artifact: summary }));
    vitest.stubGlobal("fetch", fetch);
    const { canvas, view } = mount(1);

    await act(() => view.result.current.reimport());

    expect(fetch.mock.calls.map(([url, init]) => [url, init?.body])).toEqual([
      ["/api/artifacts/a1/reimport", JSON.stringify({ base_version: 1 })],
    ]);
    expect(canvas.imported.mock.calls).toEqual([[summary]]);
    expect(view.result.current.note).toEqual({ tone: "info", text: "Tệp nguồn không đổi." });
  });
});
