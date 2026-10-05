import { describe, expect, it } from "vitest";
import { type DockView, dockShowing } from "./canvas-dock-state";

describe("whether the dock has something on show", () => {
  it.each<[DockView, boolean, boolean]>([
    ["closed", false, false],
    ["closed", true, true],
    ["list", false, true],
    ["list", true, true],
    ["canvas", false, true],
    ["canvas", true, true],
  ])("with the dock %s and a canvas being written shown %s, says %s", (view, writing, showing) => {
    expect(dockShowing(view, writing)).toBe(showing);
  });
});
