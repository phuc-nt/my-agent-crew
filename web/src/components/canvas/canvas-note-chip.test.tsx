import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import { CanvasNoteChip } from "./canvas-note-chip";

const NOTE = "[Canvas · Kế hoạch tuần]\n> chạy 5 km";

/** jsdom has no clipboard; a test that copies installs one and the hook below removes it. */
function installClipboard(writeText: (text: string) => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
}

afterEach(() => {
  Reflect.deleteProperty(navigator, "clipboard");
});

const chip = () => screen.getByRole("button", { name: vi.canvas.noteChip });
const body = () => screen.queryByTestId("canvas-note-body");
const text = () => body()?.querySelector("pre")?.textContent;

describe("CanvasNoteChip", () => {
  it("is a collapsed chip until it is pressed, with nothing of the note on screen", () => {
    render(<CanvasNoteChip note={NOTE} />);

    expect(chip()).toHaveAttribute("aria-expanded", "false");
    // Pointing at a body that is not there would send a screen reader nowhere.
    expect(chip()).not.toHaveAttribute("aria-controls");
    expect(body()).toBeNull();
    expect(screen.queryByText(/chạy 5 km/)).toBeNull();
    expect(screen.queryByRole("button", { name: vi.canvas.noteCopy })).toBeNull();
  });

  it("opens the note as it was written on a press, and closes it on the next", () => {
    render(<CanvasNoteChip note={NOTE} />);

    fireEvent.click(chip());
    expect(chip()).toHaveAttribute("aria-expanded", "true");
    expect(text()).toBe(NOTE);
    expect(chip()).toHaveAttribute("aria-controls", body()?.id);

    fireEvent.click(chip());
    expect(chip()).toHaveAttribute("aria-expanded", "false");
    expect(chip()).not.toHaveAttribute("aria-controls");
    expect(body()).toBeNull();
  });

  // The note quotes the person's canvas, and a canvas may hold anything an agent copied from
  // a web page: it is read as text, never as markup.
  it("keeps markup in the note as text", () => {
    const note = '<script>alert("x")</script>\n<img src=x onerror="alert(1)">';
    render(<CanvasNoteChip note={note} />);

    fireEvent.click(chip());

    expect(text()).toBe(note);
    expect(body()?.querySelector("script, img")).toBeNull();
  });

  it("writes a hidden character as a visible mark, and copies the note as it was", async () => {
    const raw = "[Canvas]\n> a‮b";
    const writeText = vitest.fn(() => Promise.resolve());
    installClipboard(writeText);
    render(<CanvasNoteChip note={raw} />);

    fireEvent.click(chip());
    expect(text()).toBe("[Canvas]\n> a[U+202E]b");

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.noteCopy }));
    await act(async () => {});
    expect(writeText).toHaveBeenCalledTimes(1);
    expect(writeText).toHaveBeenCalledWith(raw);
  });
});
