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
    const card = await within(results).findByRole("article", { name: /Bản tin morning/ });
    expect(within(card).getByText(vi.inbox.unread)).toBeInTheDocument();
    expect(within(results).queryByText(/Bản tin check/)).toBeNull();

    // Read now: back in the chat only the request still counts.
    await userEvent.click(screen.getByRole("button", { name: vi.inbox.back }));
    await waitFor(() => expect(inboxButton()).toHaveAccessibleName(vi.inbox.openWith(1)));
  });

  it("opens a report in its conversation to answer it, and lists no command's output", async () => {
    backend.runs = [report("morning"), report("sync", { conversation_id: null, summary: "synced 0 mail" })];
    window.location.hash = "#/inbox";
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: vi.inbox.openReport("Bản tin morning") }));
    expect(window.location.hash).toBe("#/chat/conv-morning");

    window.location.hash = "#/inbox";
    await screen.findByRole("article", { name: /Bản tin morning/ });
    expect(screen.queryByText(/Bản tin sync/)).toBeNull();
    expect(screen.queryByText("synced 0 mail")).toBeNull();
  });

  // What the chat is sent, not the start the run kept: formatted, and read in place.
  it("reads each report whole and formatted, under the agent's name and the job's", async () => {
    backend.runs = [report("morning", { title: "[lịch] Bản tin sáng · 2026-11-01 07:00" })];
    backend.reportTexts = { morning: "**Hôm nay** có 3 cuộc họp.\n\n- Họp nhóm\n\nMEDIA:/tmp/chart.png" };
    window.location.hash = "#/inbox";
    render(<App />);
    const card = await screen.findByRole("article", { name: /Bản tin sáng/ });
    expect(await within(card).findByText("Hôm nay")).toHaveProperty("tagName", "STRONG");
    expect(within(card).getByRole("listitem")).toHaveTextContent("Họp nhóm");
    expect(within(card).getByText(vi.inbox.sent(1))).toBeInTheDocument();
    expect(within(card).queryByText(/\[lịch\]|2026-11-01/)).toBeNull();
    expect(within(card).queryByText(/MEDIA:/)).toBeNull();
  });

  it("folds a long report until it is asked to show all of it", async () => {
    backend.runs = [report("long")];
    backend.reportTexts = { long: Array.from({ length: 30 }, (_, n) => `Dòng ${n}`).join("\n\n") };
    window.location.hash = "#/inbox";
    render(<App />);
    const card = await screen.findByRole("article", { name: /Bản tin long/ });
    const unfold = await within(card).findByRole("button", { name: vi.inbox.unfold });
    expect(card.querySelector(".inbox-report-body")).toHaveClass("folded");
    await userEvent.click(unfold);
    expect(card.querySelector(".inbox-report-body")).not.toHaveClass("folded");
    expect(within(card).getByRole("button", { name: vi.inbox.fold })).toHaveAttribute("aria-expanded", "true");
  });

  it("says when no job has reported anything yet", async () => {
    window.location.hash = "#/inbox";
    render(<App />);
    expect(await screen.findByText(vi.inbox.noResults)).toBeInTheDocument();
    expect(screen.getByText(vi.attentionEmpty)).toBeInTheDocument();
  });

  // A wide screen has no drawer; the sidebar's foot is always in view, over the manage button.
  it("is offered at the sidebar's foot of a wide screen too, counted the same way", async () => {
    screenWidth(false);
    backend.runs = [
      fakeRun({ id: "w", status: "awaiting_approval", conversation_id: "c9", finished_at: null }),
      report("morning"),
    ];
    render(<App />);
    await waitFor(() => expect(inboxButton()).toHaveAccessibleName(vi.inbox.openWith(2)));
    expect(inboxButton().closest(".sidebar-foot")).not.toBeNull();
    expect(screen.queryByRole("button", { name: new RegExp(vi.openConversations) })).toBeNull();

    await userEvent.click(inboxButton());
    const inbox = await screen.findByTestId("inbox-screen");
    expect(await within(inbox).findByRole("article", { name: /Bản tin morning/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: vi.inbox.back }));
    await waitFor(() => expect(inboxButton()).toHaveAccessibleName(vi.inbox.openWith(1)));
  });
});
