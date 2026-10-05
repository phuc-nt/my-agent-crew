import { fireEvent, render, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { vi } from "../../i18n/vi";
import { closeButton, frame, frameBody as body, openFrame as open } from "../../test/canvas-writing-frame";
import { CanvasView } from "./canvas-view";

const text = vi.canvas.writing;

/** The button that stands in for an image from another site until the person asks for it. */
const hold = (host: string, alt: string) =>
  within(body()).getByRole("button", { name: `${vi.markdownImage.show(host)} ${alt}` });
const copyCode = () => within(body()).getByRole("button", { name: vi.copy.code });

/** A link, an image from another site and a block of code. */
const MARKDOWN = "Xem [trang](https://example.test/a) và ![ảnh](http://a.test/x)\n\n```sh\nls -la\n```\n";

describe("what a canvas being written offers in its text", () => {
  it("offers what a saved markdown canvas does: a link that leaves the app, an image held back, code to copy", () => {
    open({ content: MARKDOWN });

    const link = within(body()).getByRole("link", { name: "trang" });
    expect(link).toHaveAttribute("href", "https://example.test/a");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(frame()).getAllByRole("link")).toEqual([link]);

    // Nothing is fetched from the other site for having been written.
    expect(body().querySelector("img")).toBeNull();
    expect(hold("a.test", "ảnh")).toHaveAttribute("title", "http://a.test/x");
    expect(within(frame()).getAllByRole("button")).toEqual([closeButton(), hold("a.test", "ảnh"), copyCode()]);
  });

  it("draws that text exactly as a saved canvas draws it", () => {
    open({ content: MARKDOWN });
    const written = body().querySelector(".canvas-view")?.outerHTML;

    const saved = render(<CanvasView text={MARKDOWN} kind="markdown" />);

    expect(written).toBeDefined();
    expect(written).toBe(saved.container.querySelector(".canvas-view")?.outerHTML);
  });

  it("offers nothing to type in, whatever the text holds", () => {
    open({ content: MARKDOWN });
    expect(within(frame()).queryByRole("textbox")).toBeNull();
    expect(frame().querySelector("input, textarea, select, [contenteditable]")).toBeNull();
  });

  it.each(["html", "svg", "mermaid", "code", "image", null])(
    "offers only its close button for a canvas of kind %s, whose links, images and code are text",
    (kind) => {
      open({ kind, content: MARKDOWN });

      expect(within(frame()).getAllByRole("button")).toEqual([closeButton()]);
      expect(within(frame()).queryByRole("link")).toBeNull();
      expect(within(frame()).queryByRole("textbox")).toBeNull();
      expect(body().querySelector("img")).toBeNull();
    },
  );

  it("offers only its close button for a markdown canvas grown so long that it is shown as its source", () => {
    open({ content: MARKDOWN.padEnd(100_000, " chữ") });

    expect(within(body()).getByText(text.long)).toBeInTheDocument();
    expect(within(frame()).getAllByRole("button")).toEqual([closeButton()]);
    expect(within(frame()).queryByRole("link")).toBeNull();
    expect(body().querySelector("img")).toBeNull();
  });
});

describe("an image from another site in a canvas being written", () => {
  // The address stands in a definition at the end of the text, which is where the next piece
  // of the canvas adds to it. Each piece is an address someone could be told of.
  const HEAD = "![biểu đồ][1]\n\n[1]: http://a.test/x";
  const image = () => within(body()).getByRole("img", { name: "biểu đồ" });

  it("is asked about again when a later piece lengthens the address the person agreed to", () => {
    const { again } = open({ content: HEAD });
    expect(body().querySelector("img")).toBeNull();
    expect(hold("a.test", "biểu đồ")).toHaveAttribute("title", "http://a.test/x");

    fireEvent.click(hold("a.test", "biểu đồ"));
    expect(image()).toHaveAttribute("src", "http://a.test/x");

    again({ content: `${HEAD}y`, updates: 3 });

    // Their yes was to `/x`. Nothing is fetched from `/xy` until they say so.
    expect(body().querySelector("img")).toBeNull();
    expect(hold("a.test", "biểu đồ")).toHaveAttribute("title", "http://a.test/xy");

    fireEvent.click(hold("a.test", "biểu đồ"));
    expect(image()).toHaveAttribute("src", "http://a.test/xy");
  });

  it("stays shown while later pieces leave its address as it was", () => {
    const { again } = open({ content: HEAD });
    fireEvent.click(hold("a.test", "biểu đồ"));
    const shown = image();

    again({ content: `${HEAD}\n\nThêm một dòng.`, updates: 3 });

    expect(image()).toBe(shown);
    expect(shown).toHaveAttribute("src", "http://a.test/x");
    expect(within(frame()).getAllByRole("button")).toEqual([closeButton()]);
  });
});
