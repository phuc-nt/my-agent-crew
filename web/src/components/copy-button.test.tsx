import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import { BubbleActions, COPIED_MS, CopyButton } from "./copy-button";

/** jsdom has no clipboard; each test installs the one it needs and removes it after. */
function installClipboard(writeText: ((text: string) => Promise<void>) | undefined) {
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: writeText ? { writeText } : undefined,
  });
}

afterEach(() => {
  vitest.useRealTimers();
  Reflect.deleteProperty(navigator, "clipboard");
  Reflect.deleteProperty(navigator, "share");
});

const reply = "**Kế hoạch**\n- ngủ trước 23:00";

describe("CopyButton", () => {
  it("writes the text as given and says 'Đã chép' for a moment", async () => {
    vitest.useFakeTimers();
    const writeText = vitest.fn(() => Promise.resolve());
    installClipboard(writeText);
    render(<CopyButton text={reply} label={vi.copy.reply} />);

    fireEvent.click(screen.getByRole("button", { name: vi.copy.reply }));
    await act(async () => {});

    // The raw markdown, not the rendered text: pasted into a notes app it keeps its shape.
    expect(writeText).toHaveBeenCalledWith(reply);
    expect(screen.getByRole("button", { name: vi.copy.copied })).toHaveTextContent(vi.copy.copied);

    act(() => vitest.advanceTimersByTime(COPIED_MS));
    expect(screen.getByRole("button", { name: vi.copy.reply })).toHaveTextContent(vi.copy.copy);
  });

  // A screen reader does not read out a changed button name, so without a live region a
  // copy that worked would pass in silence.
  it("says 'Đã chép' through a live region that is in the page before the copy", async () => {
    vitest.useFakeTimers();
    installClipboard(() => Promise.resolve());
    const { container } = render(<CopyButton text={reply} label={vi.copy.reply} />);
    const announcer = container.querySelector('[aria-live="polite"]');
    expect(announcer).toBeEmptyDOMElement();

    fireEvent.click(screen.getByRole("button", { name: vi.copy.reply }));
    await act(async () => {});
    expect(container.querySelector('[aria-live="polite"]')).toBe(announcer);
    expect(announcer).toHaveTextContent(vi.copy.copied);

    act(() => vitest.advanceTimersByTime(COPIED_MS));
    expect(announcer).toBeEmptyDOMElement();
  });

  it("shows the text to copy by hand when the browser refuses the write", async () => {
    installClipboard(() => Promise.reject(new DOMException("denied", "NotAllowedError")));
    render(<CopyButton text={reply} label={vi.copy.reply} />);

    fireEvent.click(screen.getByRole("button", { name: vi.copy.reply }));

    const fallback = await screen.findByTestId("copy-fallback");
    expect(fallback).toHaveTextContent(vi.copy.failed);
    const box = screen.getByRole("textbox", { name: vi.copy.manual });
    expect(box).toHaveValue(reply);
    expect(box).toHaveFocus();
    expect(screen.queryByRole("button", { name: vi.copy.copied })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: vi.close }));
    expect(screen.queryByTestId("copy-fallback")).toBeNull();
    // The focus goes back where it came from, not to the top of the page.
    expect(screen.getByRole("button", { name: vi.copy.reply })).toHaveFocus();
  });

  it("puts the hand-copy box away on Esc, keeps the Esc to itself, and returns the focus", async () => {
    const onDocumentKey = vitest.fn();
    document.addEventListener("keydown", onDocumentKey);
    try {
      installClipboard(undefined);
      render(<CopyButton text="uv run pytest -q" label={vi.copy.code} />);
      fireEvent.click(screen.getByRole("button", { name: vi.copy.code }));
      const box = await screen.findByRole("textbox", { name: vi.copy.manual });

      fireEvent.keyDown(box, { key: "Escape" });

      expect(screen.queryByTestId("copy-fallback")).toBeNull();
      expect(screen.getByRole("button", { name: vi.copy.code })).toHaveFocus();
      // The drawer closes on Esc; that must not happen when the Esc only meant this box.
      expect(onDocumentKey).not.toHaveBeenCalled();
    } finally {
      document.removeEventListener("keydown", onDocumentKey);
    }
  });

  it("falls back the same way where there is no clipboard at all, as over plain http", async () => {
    installClipboard(undefined);
    render(<CopyButton text="uv run pytest -q" label={vi.copy.code} />);

    fireEvent.click(screen.getByRole("button", { name: vi.copy.code }));

    expect(await screen.findByRole("textbox", { name: vi.copy.manual })).toHaveValue("uv run pytest -q");
  });
});

describe("BubbleActions", () => {
  it("offers no share button where the platform has no share sheet", () => {
    render(<BubbleActions text={reply} />);
    expect(screen.getByRole("button", { name: vi.copy.reply })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: vi.copy.share })).toBeNull();
  });

  it("hands the reply to the share sheet where there is one, and a cancel is not an error", async () => {
    const share = vitest.fn(() => Promise.reject(new DOMException("cancel", "AbortError")));
    Object.defineProperty(navigator, "share", { configurable: true, value: share });
    render(<BubbleActions text={reply} />);

    fireEvent.click(screen.getByRole("button", { name: vi.copy.share }));
    await act(async () => {});

    expect(share).toHaveBeenCalledWith({ text: reply });
    expect(screen.queryByTestId("copy-fallback")).toBeNull();
  });
});
