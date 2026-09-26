import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, FakeEventSource, fakeRun } from "./test/fake-backend";

let backend: FakeBackend;

/** A phone: the phone query matches and the wide one does not, whatever else is asked. */
function phoneScreen() {
  vitest.stubGlobal("matchMedia", (media: string) => ({
    matches: media.includes("max-width"),
    media,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

/** This runner has no `localStorage` of its own, and the strip remembers its state there. */
function memoryStorage() {
  const store = new Map<string, string>();
  vitest.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    clear: () => store.clear(),
  });
}

beforeEach(() => {
  backend = new FakeBackend();
  FakeEventSource.instances = [];
  vitest.stubGlobal("fetch", backend.fetch);
  vitest.stubGlobal("EventSource", FakeEventSource);
  phoneScreen();
  memoryStorage();
  window.location.hash = "";
});

afterEach(() => vitest.unstubAllGlobals());

const drawer = () => screen.getByRole("navigation", { hidden: true });
const menu = () => screen.getByRole("button", { name: new RegExp(vi.openConversations) });

describe("the conversation drawer on a phone", () => {
  // The search box sits in the drawer, which is inert while closed: focusing it there
  // would leave the key doing nothing anyone can see.
  it("opens around the search box when ⌘K asks for it", async () => {
    for (let n = 1; n <= 8; n++) backend.create({ title: `Cuộc ${n}` });
    render(<App />);
    await screen.findByRole("searchbox", { hidden: true });
    expect(drawer()).toHaveAttribute("inert");

    await userEvent.keyboard("{Control>}k{/Control}");

    expect(drawer()).not.toHaveAttribute("inert");
    expect(menu()).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("searchbox")).toHaveFocus();
  });

  // Escape closes the topmost layer. The strip under the drawer is not on top, and
  // collapsing it would also overwrite the choice the strip remembers.
  it("closes on Escape and leaves the activity strip as it was", async () => {
    const mine = backend.create({ title: "Có việc" });
    backend.runs = [fakeRun({ conversation_id: mine.id, summary: "Đã xong" })];
    window.localStorage.setItem("conversation-activity.expanded", "1");
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Có việc/, hidden: true }));
    const strip = await screen.findByTestId("conversation-activity");
    const toggle = within(strip).getByRole("button", { name: vi.conversationActivity.collapse });

    await userEvent.click(menu());
    expect(drawer()).not.toHaveAttribute("inert");
    await userEvent.keyboard("{Escape}");

    expect(drawer()).toHaveAttribute("inert");
    expect(menu()).toHaveFocus();
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(window.localStorage.getItem("conversation-activity.expanded")).toBe("1");

    // With nothing on top of it, the strip is the topmost layer again.
    await userEvent.keyboard("{Escape}");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  // A drawer over the page is modal: Tab and a screen reader's swipe must not wander
  // into the chat it covers.
  it("makes the chat underneath inert while it is open", async () => {
    render(<App />);
    await screen.findByText(vi.welcomeTitleFor("Agent"));
    const main = screen.getByRole("main");
    expect(main).not.toHaveAttribute("inert");
    // Nothing is waiting, so the name is just what the button does.
    expect(menu()).toHaveAccessibleName(vi.openConversations);

    await userEvent.click(menu());
    expect(main).toHaveAttribute("inert");

    await userEvent.click(within(drawer()).getByRole("button", { name: vi.closeConversations }));
    expect(main).not.toHaveAttribute("inert");
  });

  // The dot on the menu button is only there for the eye; the button's name says it too.
  it("names the work waiting behind the drawer on the button that opens it", async () => {
    backend.runs = [fakeRun({ id: "w", status: "awaiting_approval", conversation_id: "c9" })];
    render(<App />);
    await screen.findByText(vi.welcomeTitleFor("Agent"));

    await waitFor(() =>
      expect(menu()).toHaveAccessibleName(`${vi.openConversations} (${vi.manage.waiting(1)})`),
    );
  });
});
