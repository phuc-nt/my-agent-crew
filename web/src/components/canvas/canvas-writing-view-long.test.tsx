import { within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { vi } from "../../i18n/vi";
import { closeButton, frame, frameBody as body, openFrame as open } from "../../test/canvas-writing-frame";

const text = vi.canvas.writing;

/** A markdown canvas of exactly `chars` characters: a heading, then one paragraph. */
const draft = (chars: number) => `# Việc một\n\n${"chữ ".repeat(chars / 4 + 1)}`.slice(0, chars);

const heading = () => within(frame()).queryByRole("heading", { level: 1, name: "Việc một" });
const source = () => body().querySelector("pre.canvas-code");

describe("a canvas being written that has grown long", () => {
  it("is still read as markdown one character short of a hundred thousand", () => {
    const content = draft(99_999);
    expect(content).toHaveLength(99_999);
    open({ content });

    expect(heading()).toBeInTheDocument();
    expect(source()).toBeNull();
    expect(within(frame()).queryByText(text.long)).toBeNull();
  });

  it.each([100_000, 100_001, 250_000])("is shown as its source at %i characters, with a line saying why", (chars) => {
    const content = draft(chars);
    expect(content).toHaveLength(chars);
    open({ content });

    expect(source()?.textContent).toBe(content);
    expect(heading()).toBeNull();
    expect(body().querySelector("h1, p, a")).toBeNull();
    expect(within(body()).getByText(text.long)).toBeInTheDocument();
    // The line about a page or a drawing is for another reason, and is not said too.
    expect(within(frame()).queryByText(text.source)).toBeNull();
  });

  it("writes the characters that hide in a long text as marks, as the source of any canvas does", () => {
    open({ content: `${draft(100_000)}${String.fromCharCode(0x202e)}` });
    expect(source()?.textContent?.endsWith("[U+202E]")).toBe(true);
  });

  it.each(["code", "image", null])("says nothing more of a long canvas of kind %s, which is plain text at any length", (kind) => {
    open({ kind, content: draft(100_000) });

    expect(source()?.textContent).toBe(draft(100_000));
    expect(within(frame()).queryByText(text.long)).toBeNull();
    expect(within(frame()).queryByText(text.source)).toBeNull();
  });

  it.each(["html", "svg", "mermaid"])("gives a long canvas of kind %s the one line a short one has", (kind) => {
    open({ kind, content: draft(100_000) });

    expect(within(frame()).getByText(text.source)).toBeInTheDocument();
    expect(within(frame()).queryByText(text.long)).toBeNull();
  });
});

describe("a canvas being written that grows long while it shows", () => {
  it("keeps its frame, its place to scroll and the keyboard on its close button", () => {
    const { again } = open({ content: draft(99_999) }, 1);
    const [was, button, area] = [frame(), closeButton(), body()];
    expect(button).toHaveFocus();
    expect(heading()).toBeInTheDocument();

    again({ content: draft(100_000) }, 1);

    expect(source()?.textContent).toBe(draft(100_000));
    expect(within(body()).getByText(text.long)).toBeInTheDocument();
    expect(frame()).toBe(was);
    expect(body()).toBe(area);
    expect(closeButton()).toBe(button);
    expect(button).toHaveFocus();
  });

  it("does not go back to markdown for a later piece", () => {
    const { again } = open({ content: draft(100_000) });

    again({ content: draft(100_400) });

    expect(source()?.textContent).toBe(draft(100_400));
    expect(heading()).toBeNull();
    expect(within(body()).getAllByText(text.long)).toHaveLength(1);
  });
});
