import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { memoryStorage } from "../test/memory-storage";
import { useCanvasWidth } from "./use-canvas-width";

let store: Map<string, string>;

beforeEach(() => {
  store = memoryStorage();
  vitest.stubGlobal("innerWidth", 1440);
});

afterEach(() => vitest.unstubAllGlobals());

function resizeWindow(width: number) {
  vitest.stubGlobal("innerWidth", width);
  act(() => {
    window.dispatchEvent(new Event("resize"));
  });
}

// At 1440 px the sidebar's 272 px leave 1168 px: half is 584, and the most is 1168 - 360.
describe("the width of the canvas beside a wide conversation", () => {
  it("takes half the room beside the sidebar until the person chooses", () => {
    const { result } = renderHook(useCanvasWidth);

    expect(result.current).toMatchObject({ width: 584, min: 360, max: 808 });
  });

  it("keeps both the canvas and the conversation at least 360 px wide", () => {
    const { result } = renderHook(useCanvasWidth);

    act(() => result.current.resize(100));
    expect(result.current.width).toBe(360);
    act(() => result.current.resize(5000));
    expect(result.current.width).toBe(808);
  });

  it("remembers a width for the next visit only when told to keep it", () => {
    const { result, unmount } = renderHook(useCanvasWidth);

    act(() => result.current.resize(700));
    expect(store.has("canvas-width")).toBe(false);
    act(() => result.current.resize(640.4, true));
    unmount();

    expect(store.get("canvas-width")).toBe("640");
    expect(renderHook(useCanvasWidth).result.current.width).toBe(640);
  });

  it("fits a kept width to a narrower window, and gives it back when the window widens", () => {
    const { result } = renderHook(useCanvasWidth);
    act(() => result.current.resize(700, true));

    resizeWindow(1200);
    expect(result.current).toMatchObject({ width: 568, max: 568 });
    resizeWindow(1440);
    expect(result.current.width).toBe(700);
  });

  it("follows the window while the person has not chosen", () => {
    const { result } = renderHook(useCanvasWidth);

    resizeWindow(1200);

    expect(result.current.width).toBe(464);
  });

  it("never makes the canvas narrower than 360 px, even beside a narrow conversation", () => {
    vitest.stubGlobal("innerWidth", 900);
    const { result } = renderHook(useCanvasWidth);

    expect(result.current).toMatchObject({ width: 360, max: 360 });
  });

  it("ignores a kept width that is not a number", () => {
    store.set("canvas-width", JSON.stringify("wide"));

    expect(renderHook(useCanvasWidth).result.current.width).toBe(584);
  });

  it("ignores a kept width too large to be a number", () => {
    store.set("canvas-width", "1e999");

    expect(renderHook(useCanvasWidth).result.current.width).toBe(584);
  });

  it("measures the room beside the sidebar the stylesheet sets", () => {
    document.documentElement.style.setProperty("--sidebar-width", "300px");
    try {
      expect(renderHook(useCanvasWidth).result.current).toMatchObject({ width: 570, max: 780 });
    } finally {
      document.documentElement.style.removeProperty("--sidebar-width");
    }
  });
});
