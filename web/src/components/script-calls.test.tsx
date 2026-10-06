import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { NestedToolCall } from "../api/types";
import { vi } from "../i18n/vi";
import { ScriptCalls } from "./script-calls";

function call(overrides: Partial<NestedToolCall> = {}): NestedToolCall {
  return {
    name: "mcp__notion__search",
    arguments: { query: "kế hoạch" },
    ok: true,
    output: "3 trang",
    ms: 120,
    cost_usd: null,
    metered: false,
    ...overrides,
  };
}

function show(calls: NestedToolCall[]) {
  const { unmount } = render(<ScriptCalls calls={calls} />);
  const list = screen.getByTestId("script-calls") as HTMLDetailsElement;
  const rows = within(list).getAllByTestId("script-call");
  return { list, summary: list.querySelector("summary")!, rows, unmount };
}

describe("what a script called on its own", () => {
  it("says how many calls there were, and how many failed only when one did", () => {
    const clean = show([call(), call(), call()]);
    expect(clean.summary).toHaveTextContent(/^Script đã gọi công cụ 3 lần$/);
    clean.unmount();

    const broken = show([call(), call({ ok: false }), call({ ok: false })]);
    expect(broken.summary).toHaveTextContent(/^Script đã gọi công cụ 3 lần · 2 lần lỗi$/);
  });

  // Two dozen calls opened would push the rest of the run off the screen.
  it("stays folded until its line is clicked, and folds again on the next click", async () => {
    const { list, summary, rows } = show([call(), call()]);
    expect(list.open).toBe(false);
    expect(rows[0]).not.toBeVisible();

    await userEvent.click(summary);
    expect(list.open).toBe(true);
    expect(rows[0]).toBeVisible();
    expect(rows[1]).toBeVisible();

    await userEvent.click(summary);
    expect(list.open).toBe(false);
  });

  it("lists every call in the order the script made it, the same call twice as two rows", () => {
    const { list, rows } = show([call(), call({ name: "workspace_read" }), call()]);

    expect(list.querySelector("ol")?.children).toHaveLength(3);
    expect(rows.map((row) => row.querySelector("code")?.textContent)).toEqual([
      "mcp__notion__search",
      "workspace_read",
      "mcp__notion__search",
    ]);
  });

  it("gives a call its name, what it was called with and how long it took", () => {
    const { rows } = show([call({ arguments: { query: "kế hoạch", limit: 5 }, ms: 1_500 }), call({ arguments: {}, ms: 40 })]);

    expect(rows[0].querySelector(".script-call-head")).toHaveTextContent(/^mcp__notion__search1\.5 giây$/);
    expect(rows[0].querySelectorAll(".script-call-line")[0]).toHaveTextContent(/^query=kế hoạch, limit=5$/);
    // A call with nothing to say still has its line, so the rows read alike.
    expect(rows[1].querySelector(".script-call-head")).toHaveTextContent(/^mcp__notion__search40 ms$/);
    expect(rows[1].querySelectorAll(".script-call-line")[0]).toHaveTextContent(/^—$/);
  });

  it("marks the call that failed, and no other", () => {
    const { rows } = show([call(), call({ ok: false, output: "không tìm thấy" })]);

    expect(rows[0]).toHaveAttribute("data-ok", "true");
    expect(rows[0].querySelector(".step-state")).toBeNull();
    expect(rows[1]).toHaveAttribute("data-ok", "false");
    expect(rows[1].querySelector(".step-state.failed")).toHaveTextContent(vi.toolFailed);
  });

  it("prices a call that paid a model, says so when no price came, and says nothing on a free one", () => {
    const { rows } = show([
      call({ metered: true, cost_usd: 0.004 }),
      call({ metered: true, cost_usd: null }),
      call({ metered: false, cost_usd: null }),
      // Not charged, so not shown as charged, whatever figure rode along.
      call({ metered: false, cost_usd: 0.5 }),
    ]);

    expect(within(rows[0]).getByTestId("script-call-cost")).toHaveTextContent(/^Có gọi model · \$0\.0040$/);
    expect(within(rows[1]).getByTestId("script-call-cost")).toHaveTextContent(/^Có gọi model · không rõ giá$/);
    expect(within(rows[2]).queryByTestId("script-call-cost")).toBeNull();
    expect(within(rows[3]).queryByTestId("script-call-cost")).toBeNull();
  });

  it("shows what came back to the script, and no empty line when nothing did", () => {
    const { rows } = show([call({ output: "3 trang: Kế hoạch tuần, Báo cáo, Ghi chú" }), call({ output: "" })]);

    expect(within(rows[0]).getByTestId("script-call-output")).toHaveTextContent(/^3 trang: Kế hoạch tuần, Báo cáo, Ghi chú$/);
    expect(within(rows[1]).queryByTestId("script-call-output")).toBeNull();
    expect(rows[1].querySelectorAll(".script-call-line")).toHaveLength(1);
  });

  // The order a person reads a call in: with what, at what price, then what came back.
  it("puts the price of a call between what it was called with and what came back", () => {
    const { rows } = show([call({ metered: true, cost_usd: 0.01 })]);

    const lines = [...rows[0].querySelectorAll(".script-call-line")].map((line) => line.textContent);
    expect(lines).toEqual(["query=kế hoạch", "Có gọi model · $0.01", "3 trang"]);
  });
});
