import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import type { DelegateCanvas } from "../../lib/delegate-result";
import type { CanvasLinks } from "./canvas-card";
import { DelegateCanvases } from "./delegate-canvases";

const PLAN = "00ff00ff00ff";
const NOTE = "0123456789ab";
const SHOP = "ba9876543210";
const { card } = vi.canvas;

const REPORT: DelegateCanvas = { id: PLAN, version: 2, title: "Báo cáo tuần" };
const ANNEX: DelegateCanvas = { id: NOTE, version: 1, title: "Phụ lục" };

/** What the thread knows of canvases, with every call recorded; by default it knows nothing. */
function links(known: { titles?: Record<string, string>; gone?: string[] } = {}) {
  return {
    titleOf: vitest.fn((id: string) => known.titles?.[id] ?? null),
    isGone: vitest.fn((id: string) => (known.gone ?? []).includes(id)),
    verify: vitest.fn(),
    open: vitest.fn(),
  } satisfies CanvasLinks;
}

const chips = () => screen.queryAllByTestId("delegate-canvas");
const show = (canvases: DelegateCanvas[], canvas: CanvasLinks) => render(<DelegateCanvases canvases={canvases} canvas={canvas} />);

describe("the canvases a handed-off task wrote", () => {
  it("are named in the order the result gives them, each with the version it was left at and a way to open it", () => {
    show([REPORT, ANNEX], links());

    expect(chips().map((chip) => chip.textContent)).toEqual([`Báo cáo tuầnv2${card.open}`, `Phụ lụcv1${card.open}`]);
    expect(within(chips()[0]).getByRole("button", { name: card.openLabel("Báo cáo tuần") })).toBeInTheDocument();
    expect(within(chips()[1]).getByRole("button", { name: card.openLabel("Phụ lục") })).toBeInTheDocument();
  });

  it("are a list that says what it holds", () => {
    show([REPORT, ANNEX], links());

    const list = screen.getByRole("list", { name: vi.canvas.delegateCanvases });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
  });

  it("open the one whose button is pressed, and no other", () => {
    const canvas = links();
    show([REPORT, ANNEX], canvas);

    fireEvent.click(screen.getByRole("button", { name: card.openLabel("Phụ lục") }));

    expect(canvas.open.mock.calls).toEqual([[NOTE]]);
  });

  it("go by the title the thread knows a canvas by, then by the one in the result, then by none", () => {
    const canvas = links({ titles: { [PLAN]: "Báo cáo đã đổi tên" } });
    show([REPORT, ANNEX, { id: SHOP, version: 4, title: "" }], canvas);

    expect(chips().map((chip) => chip.querySelector(".delegate-canvas-title")?.textContent)).toEqual([
      "Báo cáo đã đổi tên",
      "Phụ lục",
      card.untitled,
    ]);
    expect(screen.getByRole("button", { name: card.openLabel("Báo cáo đã đổi tên") })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: card.openLabel(card.untitled) })).toBeInTheDocument();
  });

  it("write out what nobody would see in a title, and draw markup in one as words", () => {
    show(
      [
        { id: PLAN, version: 1, title: "an\u{202E}toàn" },
        { id: NOTE, version: 1, title: '<img src=x onerror="alert(1)"><b>đậm</b>' },
      ],
      links(),
    );

    const titles = chips().map((chip) => chip.querySelector(".delegate-canvas-title") as HTMLElement);
    expect(titles[0].textContent).toBe("an[U+202E]toàn");
    expect(screen.getByRole("button", { name: card.openLabel("an[U+202E]toàn") })).toBeInTheDocument();
    expect(titles[1].textContent).toBe('<img src=x onerror="alert(1)"><b>đậm</b>');
    expect(titles[1].querySelector("img, b")).toBeNull();
  });

  it("ask once whether each canvas is still there, and again only for one not shown before", () => {
    const canvas = links();
    const view = show([REPORT, ANNEX], canvas);
    expect(canvas.verify.mock.calls).toEqual([[PLAN], [NOTE]]);

    view.rerender(<DelegateCanvases canvases={[{ ...REPORT }, { ...ANNEX }]} canvas={canvas} />);
    expect(canvas.verify).toHaveBeenCalledTimes(2);

    view.rerender(<DelegateCanvases canvases={[REPORT, ANNEX, { id: SHOP, version: 1, title: "Mua sắm" }]} canvas={canvas} />);
    expect(canvas.verify.mock.calls).toEqual([[PLAN], [NOTE], [SHOP]]);
  });

  it("say a canvas the server no longer has is deleted, with nothing to open, beside one that still is", () => {
    const canvas = links({ gone: [PLAN] });
    show([REPORT, ANNEX], canvas);

    const [gone, kept] = chips();
    expect(gone).toHaveTextContent("Báo cáo tuần");
    expect(within(gone).getByText(vi.canvas.gone)).toBeInTheDocument();
    expect(within(gone).queryByRole("button")).toBeNull();
    expect(gone).not.toHaveTextContent("v2");
    expect(within(kept).getByRole("button", { name: card.openLabel("Phụ lục") })).toBeInTheDocument();
    expect(kept).not.toHaveTextContent(vi.canvas.gone);
  });

  it("draw both lines of a result that names one canvas twice", () => {
    const canvas = links();
    show([REPORT, { ...REPORT, version: 3 }], canvas);

    expect(chips().map((chip) => chip.textContent)).toEqual([`Báo cáo tuầnv2${card.open}`, `Báo cáo tuầnv3${card.open}`]);
  });

  it("draw nothing for a task that wrote none, and ask the server nothing", () => {
    const canvas = links();
    const { container } = show([], canvas);

    expect(container).toBeEmptyDOMElement();
    expect(canvas.verify).not.toHaveBeenCalled();
  });
});
