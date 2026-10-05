import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import type { WritingItem } from "../../lib/canvas-writing";
import { CanvasWritingCard } from "./canvas-writing-card";

const text = vi.canvas.writing;

const item = (fields: Partial<WritingItem> = {}): WritingItem => ({
  key: 7,
  callId: null,
  updates: 1,
  rewrite: false,
  id: null,
  title: null,
  kind: null,
  content: "",
  bytes: 0,
  ...fields,
});

function draw(fields: Partial<WritingItem> = {}) {
  const onShow = vitest.fn();
  render(<CanvasWritingCard item={item(fields)} onShow={onShow} />);
  return onShow;
}

const card = () => screen.getByTestId("canvas-writing-card");

describe("the card of a canvas the agent is still writing", () => {
  it("says a new canvas is being written, under the title it has so far", () => {
    draw({ title: "Kế hoạch tuần" });

    expect(within(card()).getByText("Kế hoạch tuần")).toBeInTheDocument();
    expect(within(card()).getByText(text.creating)).toBeInTheDocument();
    expect(within(card()).queryByText(text.rewriting)).toBeNull();
  });

  it("says a canvas is being written again", () => {
    draw({ rewrite: true, id: "0123456789ab", title: "Ghi chú" });

    expect(within(card()).getByText("Ghi chú")).toBeInTheDocument();
    expect(within(card()).getByText(text.rewriting)).toBeInTheDocument();
    expect(within(card()).queryByText(text.creating)).toBeNull();
  });

  it("stands a plain word in for a title not written yet", () => {
    draw();
    expect(card().querySelector(".canvas-card-title")).toHaveTextContent(text.untitledNew);
  });

  it("stands another in for the title of a canvas written again that the tab does not know", () => {
    draw({ rewrite: true });
    expect(card().querySelector(".canvas-card-title")?.textContent).toBe(text.untitled);
  });

  it("writes the characters that hide in a title as marks", () => {
    draw({ title: `a${String.fromCharCode(0x202e)}b` });
    expect(within(card()).getByText("a[U+202E]b")).toBeInTheDocument();
  });

  it("names the kind once it is known", () => {
    draw({ title: "Trang", kind: "html" });
    expect(card().querySelector(".badge")).toHaveTextContent(vi.canvas.kinds.html);
  });

  it("names no kind before that", () => {
    draw({ title: "Trang" });
    expect(card().querySelector(".badge")).toBeNull();
  });

  it("says how much has been written, in a line that is not read out as it changes", () => {
    draw({ content: "x".repeat(2048), bytes: 2048 });

    const size = within(card()).getByText(text.written("2 KB"));
    expect(size).toHaveAttribute("aria-live", "off");
  });

  it("keeps its moving dots from being read out", () => {
    draw();
    expect(card().querySelector(".writing-dots")).toHaveAttribute("aria-hidden", "true");
  });

  it("offers the way to watch it, which names the canvas and asks for this very one", () => {
    const onShow = draw({ title: "Kế hoạch tuần" });

    const button = within(card()).getByRole("button", { name: text.showLabel("Kế hoạch tuần") });
    expect(button).toHaveTextContent(text.show);
    fireEvent.click(button);

    expect(onShow).toHaveBeenCalledTimes(1);
    expect(onShow).toHaveBeenCalledWith(7);
  });

  it("shows none of the text being written", () => {
    draw({ title: "Kế hoạch", content: "mật khẩu là 1234", bytes: 20 });
    expect(card()).not.toHaveTextContent("mật khẩu");
  });
});
