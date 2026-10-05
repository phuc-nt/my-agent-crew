import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import { LIVE_PREVIEW_KEY as KEY, freshLivePreview } from "../../test/live-preview";
import { refusingStorage } from "../../test/memory-storage";
import { LivePreviewSetting } from "./live-preview-setting";

const text = vi.canvas.writing;
let store: Map<string, string>;

beforeEach(() => {
  store = freshLivePreview();
});

afterEach(() => {
  cleanup();
  vitest.unstubAllGlobals();
});

const box = () => screen.getByRole("checkbox", { name: text.preview });
const tabOnly = () => screen.queryByRole("status");

describe("the switch for watching a canvas be written", () => {
  it("is a checkbox by its name, on to begin with, that says the choice is this device's", () => {
    render(<LivePreviewSetting />);

    expect(box()).toBeChecked();
    expect(screen.getByText(text.previewDevice)).toBeInTheDocument();
    expect(tabOnly()).toBeNull();
    expect(screen.getByRole("region", { name: vi.canvas.tab })).toContainElement(box());
  });

  it("stores the word off when turned off, and nothing once turned on again", () => {
    render(<LivePreviewSetting />);

    fireEvent.click(box());
    expect(box()).not.toBeChecked();
    expect([...store]).toEqual([[KEY, "off"]]);
    expect(tabOnly()).toBeNull();

    fireEvent.click(box());
    expect(box()).toBeChecked();
    expect(store.size).toBe(0);
  });

  it("comes up off on a device that turned it off", () => {
    store.set(KEY, "off");

    render(<LivePreviewSetting />);

    expect(box()).not.toBeChecked();
  });

  it("takes the choice where the browser will not store it, and says the tab alone keeps it", () => {
    refusingStorage();
    render(<LivePreviewSetting />);
    expect(tabOnly()).toBeNull();

    fireEvent.click(box());

    expect(box()).not.toBeChecked();
    expect(tabOnly()).toHaveTextContent(text.previewTabOnly);
    expect(screen.getByText(text.previewDevice)).toBeInTheDocument();
  });
});
