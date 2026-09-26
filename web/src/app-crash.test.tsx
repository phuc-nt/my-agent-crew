import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend } from "./test/fake-backend";

// The conversation list stands in for any part of the chat outside the thread and the
// activity column, which carry boundaries of their own.
vitest.mock("./components/conversation-list", () => ({
  ConversationList: () => {
    throw new Error("vỡ");
  },
}));

beforeEach(() => {
  vitest.stubGlobal("fetch", new FakeBackend().fetch);
  vitest.spyOn(console, "error").mockImplementation(() => undefined);
  window.location.hash = "";
});

afterEach(() => vitest.unstubAllGlobals());

describe("a chat screen that breaks", () => {
  // Without a boundary above the chat, React unmounts the root and leaves a blank page
  // with nothing to read and nothing to press.
  it("shows what broke and a way to reload instead of a blank page", () => {
    render(<App />);

    expect(screen.getByRole("alert")).toHaveTextContent(vi.crashed);
    expect(screen.getByRole("alert")).toHaveTextContent("vỡ");
    expect(screen.getByRole("button", { name: vi.reload })).toBeInTheDocument();
  });
});
