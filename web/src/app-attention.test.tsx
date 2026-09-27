import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, FakeEventSource, fakeApproval, fakeRun } from "./test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  FakeEventSource.instances = [];
  vitest.stubGlobal("fetch", backend.fetch);
  vitest.stubGlobal("EventSource", FakeEventSource);
  window.location.hash = "";
  document.title = "My Agent Crew";
});

afterEach(() => vitest.unstubAllGlobals());

describe("App requests waiting on the person", () => {
  // The loop this exists for: a run waits, the tab says so from the background, one click
  // lands where it is decided, and deciding it clears every count without opening the chat.
  it("counts a waiting request in the title, lands on it and settles it in place", async () => {
    const expires = new Date(Date.now() + 5 * 60_000).toISOString();
    const pending_approval = fakeApproval({ status: "pending", resolved_at: null, expires_at: expires });
    const c = backend.create({ title: "Chờ duyệt", status: "awaiting_approval", pending_approval });
    const waitingRun = fakeRun({ id: "w", status: "awaiting_approval", finished_at: null, conversation_id: c.id });
    backend.runs = [waitingRun];
    render(<App />);

    await waitFor(() => expect(document.title).toBe("(1) My Agent Crew"));
    await userEvent.click(screen.getByRole("button", { name: /Quản lý/ }));
    await waitFor(() => expect(window.location.hash).toBe("#/manage/approvals"));

    const attention = screen.getByTestId("attention");
    const bar = await within(attention).findByRole("group", { name: new RegExp(`^${vi.attentionAwaiting("Agent")}`) });
    // What the server reports once the resumed turn is over.
    backend.nextTurn = [{ type: "done", spent_usd: 0, unknown_cost_calls: 0 }];
    backend.runs = [{ ...waitingRun, status: "done", finished_at: "2026-09-19T08:01:00Z" }];
    await userEvent.click(within(bar).getByRole("button", { name: vi.approve }));

    await waitFor(() => expect(document.title).toBe("My Agent Crew"));
    expect(within(attention).queryByTestId("attention-row")).not.toBeInTheDocument();
    expect(backend.requests.some((r) => r.method === "POST" && r.path === `/conversations/${c.id}/approvals/ap1`)).toBe(true);
    expect(window.location.hash).toBe("#/manage/approvals");
    expect(screen.getByRole("button", { name: vi.approvalsTab })).toBeInTheDocument();
  });

  it("lands on the activity page when nothing waits on a decision", async () => {
    backend.runs = [fakeRun({ id: "broke", status: "error" })];
    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Quản lý/ })).toHaveTextContent("1"));

    await userEvent.click(screen.getByRole("button", { name: /Quản lý/ }));

    await waitFor(() => expect(window.location.hash).toBe("#/manage/activity"));
    expect(document.title).toBe("My Agent Crew");
  });
});
