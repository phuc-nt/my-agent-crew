import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { resetInboxRead } from "./lib/inbox-read";
import { FakeBackend, FakeEventSource, fakeRun } from "./test/fake-backend";

let backend: FakeBackend;

function screenWidth(phone: boolean) {
  vitest.stubGlobal("matchMedia", (media: string) => ({
    matches: phone && media.includes("max-width"),
    media,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

function memoryStorage() {
  const store = new Map<string, string>();
  vitest.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
  });
}

beforeEach(() => {
  backend = new FakeBackend();
  FakeEventSource.instances = [];
  vitest.stubGlobal("fetch", backend.fetch);
  vitest.stubGlobal("EventSource", FakeEventSource);
  screenWidth(true);
  memoryStorage();
  resetInboxRead();
  window.location.hash = "";
});

afterEach(() => vitest.unstubAllGlobals());

const report = (id: string, overrides = {}) =>
  fakeRun({ id, source: `job:${id}`, title: `Bản tin ${id}`, conversation_id: `conv-${id}`, summary: `Nội dung ${id}`, ...overrides });

const inboxButton = () => screen.getByRole("button", { name: new RegExp(vi.inbox.open) });

describe("the inbox on a phone", () => {
  it("counts what waits and what the jobs reported, and lists both once opened", async () => {
    backend.runs = [
      fakeRun({ id: "w", status: "awaiting_approval", conversation_id: "c9", finished_at: null }),
      report("morning", { finished_at: "2026-11-01T00:05:00Z" }),
      report("check", { summary: "OK", finished_at: "2026-11-01T00:06:00Z" }),
    ];
    render(<App />);
    await waitFor(() => expect(inboxButton()).toHaveAccessibleName(vi.inbox.openWith(2)));
    expect(screen.getByTestId("inbox-count")).toHaveTextContent("2");

    await userEvent.click(inboxButton());

    const inbox = await screen.findByTestId("inbox-screen");
    expect(window.location.hash).toBe("#/inbox");
    expect(within(inbox).getByRole("region", { name: vi.attention })).toBeInTheDocument();
    const results = within(inbox).getByRole("region", { name: vi.inbox.results });
    const card = await within(results).findByRole("button", { name: /Bản tin morning/ });
    expect(within(card).getByText(vi.inbox.unread)).toBeInTheDocument();
    expect(within(results).queryByText(/Bản tin check/)).toBeNull();

    // Read now: back in the chat only the request still counts.
    await userEvent.click(screen.getByRole("button", { name: vi.inbox.back }));
    await waitFor(() => expect(inboxButton()).toHaveAccessibleName(vi.inbox.openWith(1)));
  });

  it("opens a result in its conversation, or on its run's page when it has none", async () => {
    backend.runs = [report("morning"), report("script", { conversation_id: null })];
    window.location.hash = "#/inbox";
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Bản tin morning/ }));
    expect(window.location.hash).toBe("#/chat/conv-morning");

    window.location.hash = "#/inbox";
    await userEvent.click(await screen.findByRole("button", { name: /Bản tin script/ }));
    expect(window.location.hash).toBe("#/manage/activity/script");
  });

  it("says when no job has reported anything yet", async () => {
    window.location.hash = "#/inbox";
    render(<App />);
    expect(await screen.findByText(vi.inbox.noResults)).toBeInTheDocument();
    expect(screen.getByText(vi.attentionEmpty)).toBeInTheDocument();
  });

  // A wide screen has the manage button's counts in its sidebar, always in view.
  it("is not offered in the header of a wide screen", async () => {
    screenWidth(false);
    backend.runs = [report("morning")];
    render(<App />);
    await screen.findByText(vi.welcomeTitleFor("Agent"));
    expect(screen.queryByRole("button", { name: new RegExp(vi.inbox.open) })).toBeNull();
  });
});
