// A waiting `computer_act` call said in one line for each of its nine kinds, from the
// arguments the server keeps (`desktop/act.py`); one this cannot read says nothing, and the
// raw arguments under it stay the whole truth.
import { describe, expect, it } from "vitest";
import { ACT_TOOL, coordinate, desktopCallLine } from "./desktop-call";

const F = "00000000000000a1-1456x910-1";
const line = (args: Record<string, unknown>) => desktopCallLine(ACT_TOOL, { app: "Notes", frame_id: F, ...args });

describe("a waiting desktop action", () => {
  it.each([
    [{ kind: "click", ref: "e12", name: "Lưu" }, "Bấm «Lưu» (e12) trong Notes"],
    [{ kind: "click", ref: "e12" }, "Bấm phần tử e12 trong Notes"],
    [{ kind: "click", x: 120, y: 48.5 }, "Bấm tại điểm (120, 48.5) trong Notes"],
    [{ kind: "double_click", x: 10.256, y: 3 }, "Bấm đúp tại điểm (10.26, 3) trong Notes"],
    [{ kind: "right_click", ref: "e3", name: "Tệp" }, "Bấm chuột phải «Tệp» (e3) trong Notes"],
    [{ kind: "drag", x: 1, y: 2, to_x: 300, to_y: 400 }, "Kéo từ điểm (1, 2) tới điểm (300, 400) trong Notes"],
    [{ kind: "scroll", x: 700, y: 450, dy: -3 }, "Cuộn 0 dòng ngang, -3 dòng dọc tại điểm (700, 450) trong Notes"],
    [{ kind: "scroll", x: 700, y: 450, dx: 2, dy: 0 }, "Cuộn 2 dòng ngang, 0 dòng dọc tại điểm (700, 450) trong Notes"],
    [{ kind: "type", text: "Mua sữa\nvà bánh" }, "Gõ «Mua sữa và bánh» vào chỗ đang có con trỏ trong Notes"],
    [{ kind: "set_value", ref: "e7", text: "42" }, "Đặt «42» vào phần tử e7 trong Notes"],
    [{ kind: "key", keys: "cmd+s" }, "Nhấn cmd+s trong Notes"],
    [{ kind: "focus_app" }, "Đưa Notes lên trước màn hình"],
  ])("reads %j as one line", (args, said) => {
    expect(line(args)).toBe(said);
    expect(said).not.toContain("\n");
  });

  it("covers each kind the tool has", () => {
    const kinds = ["click", "double_click", "right_click", "drag", "scroll", "type", "set_value", "key", "focus_app"];
    const read = { ref: "e1", x: 1, y: 1, to_x: 2, to_y: 2, text: "a", keys: "return" };
    for (const kind of kinds) expect(line({ kind, ...read })).not.toBeNull();
  });

  it("is said by the element where it names one, and at no point", () => {
    expect(line({ kind: "click", ref: "e12", name: "Lưu", x: 5, y: 5 })).toBe("Bấm «Lưu» (e12) trong Notes");
  });

  it("keeps its marks of a quote out of what it quotes", () => {
    expect(line({ kind: "type", text: "«hi»" })).toBe("Gõ «hi» vào chỗ đang có con trỏ trong Notes");
  });

  it.each([
    ["no application", { kind: "focus_app", app: "" }],
    ["a kind not known here", { kind: "swipe", x: 1, y: 1 }],
    ["a click at no point and on no element", { kind: "click" }],
    ["a drag with no end", { kind: "drag", x: 1, y: 2 }],
    ["a scroll at no point", { kind: "scroll", dy: 3 }],
    ["a value with no element", { kind: "set_value", text: "x" }],
    ["a key with no keys", { kind: "key" }],
    ["a point that is not a number", { kind: "click", x: "10", y: 5 }],
  ])("says nothing for %s", (_what, args) => {
    expect(line(args)).toBeNull();
  });

  it("says nothing for another tool, or for arguments that are no mapping", () => {
    expect(desktopCallLine("browser_act", { kind: "click", app: "Notes", x: 1, y: 1 })).toBeNull();
    for (const args of [null, "click", ["click"], 3]) expect(desktopCallLine(ACT_TOOL, args)).toBeNull();
  });
});

describe("a coordinate", () => {
  it("is written to the hundredth, whole when it is whole", () => {
    expect([coordinate(3), coordinate(3.5), coordinate(3.456), coordinate(-0.5), coordinate(1e3)]).toEqual(["3", "3.5", "3.46", "-0.5", "1000"]);
  });

  it("is nothing for what is not a number", () => {
    for (const value of ["3", Number.NaN, Number.POSITIVE_INFINITY, null, undefined]) expect(coordinate(value)).toBe("");
  });
});
