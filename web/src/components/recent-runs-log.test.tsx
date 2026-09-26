import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { FakeBackend, coachAgent, fakeAgent, fakeRun } from "../test/fake-backend";
import { RecentRunsLog } from "./recent-runs-log";

let backend: FakeBackend;

/** This runner has no `localStorage` of its own, so the tests bring one. */
function useMemoryStorage() {
  const store = new Map<string, string>();
  vitest.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    clear: () => store.clear(),
  });
}

beforeEach(() => {
  useMemoryStorage();
  backend = new FakeBackend();
  backend.agents = [fakeAgent, coachAgent];
  vitest.stubGlobal("fetch", backend.fetch);
});
afterEach(() => vitest.unstubAllGlobals());

function show(streamed: RunInfo[] = []) {
  return render(
    <RecentRunsLog
      streamed={streamed}
      agents={[fakeAgent, coachAgent]}
      agentName={(id) => (id === "coach" ? "HLV" : "Agent")}
      onOpenConversation={() => undefined}
      onOpenRun={() => undefined}
      onBackToChat={() => undefined}
    />,
  );
}

const chip = (group: string, name: string) =>
  within(screen.getByRole("group", { name: group })).getByRole("button", { name });
const runsAsked = () => backend.requests.filter((r) => r.path.startsWith("/activity/runs?")).map((r) => r.path);
const many = (n: number, agent = "default") =>
  Array.from({ length: n }, (_, i) =>
    fakeRun({ id: `${agent}-${i}`, agent_id: agent, started_at: new Date(Date.UTC(2026, 8, 19, 8, 0, n - i)).toISOString() }),
  );

describe("the recent runs log", () => {
  // The stream's page is the busiest agent's; a quiet one's runs only exist on the server.
  it("asks the server for one agent's runs when its chip is chosen", async () => {
    backend.runs = [...many(3), ...many(2, "coach")];
    show(many(3));
    await waitFor(() => expect(screen.getAllByTestId("run-card")).toHaveLength(5));

    await userEvent.click(chip(vi.runFilters.agent, coachAgent.name));

    await waitFor(() => expect(screen.getAllByTestId("run-card")).toHaveLength(2));
    expect(runsAsked()).toContain("/activity/runs?limit=100&agent_id=coach");
  });

  it("narrows by status and source together without asking again", async () => {
    backend.runs = [
      fakeRun({ id: "a", source: "chat", status: "error", title: "Lỗi web" }),
      fakeRun({ id: "b", source: "job:default/brief", status: "error", title: "Lỗi lịch" }),
      fakeRun({ id: "c", source: "job:default/brief", status: "done", title: "Lịch xong" }),
    ];
    show();
    await screen.findByText(/Lịch xong/);
    const asked = runsAsked().length;

    await userEvent.click(chip(vi.runFilters.status, vi.runStatus.error));
    await userEvent.click(chip(vi.runFilters.source, "Lịch"));

    expect(screen.getAllByTestId("run-card")).toHaveLength(1);
    expect(screen.getByText(/Lỗi lịch/)).toBeInTheDocument();
    expect(runsAsked()).toHaveLength(asked);
  });

  it("says when nothing matches, and clears the chips on request", async () => {
    backend.runs = [fakeRun({ status: "done" })];
    show();
    await screen.findByTestId("run-card");

    await userEvent.click(chip(vi.runFilters.status, vi.runStatus.halted));
    expect(screen.getByText(vi.runFilters.none)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: vi.runFilters.clear }));

    expect(screen.getByTestId("run-card")).toBeInTheDocument();
  });

  it("remembers the chips for the next visit", async () => {
    backend.runs = [fakeRun({ status: "error" })];
    const { unmount } = show();
    await userEvent.click(await screen.findByRole("button", { name: vi.runStatus.error }));
    unmount();

    show();

    expect(chip(vi.runFilters.status, vi.runStatus.error)).toHaveAttribute("aria-pressed", "true");
  });

  // A private window, or a browser with site data blocked, has no storage to read.
  it("still filters where the browser refuses to remember anything", async () => {
    vitest.stubGlobal("localStorage", undefined);
    backend.runs = [fakeRun({ id: "x", status: "error" }), fakeRun({ id: "y", status: "done" })];
    show();
    await waitFor(() => expect(screen.getAllByTestId("run-card")).toHaveLength(2));

    await userEvent.click(chip(vi.runFilters.status, vi.runStatus.done));

    expect(screen.getAllByTestId("run-card")).toHaveLength(1);
  });

  it("reaches further back a step at a time and stops at the server's ceiling", async () => {
    backend.runs = many(600);
    show();
    // Found by text: a role query weighs every one of the hundreds of cards on screen,
    // which made this test slow enough to time out on a busy machine.
    const more = () => screen.queryByText(vi.runFilters.more, { selector: "button" });
    // The button is disabled while a step loads; a click then would ask for nothing.
    const reach = async (limit: number) => {
      await waitFor(() => expect(more()).toBeEnabled());
      await userEvent.click(more() as HTMLElement);
      await waitFor(() => expect(runsAsked()).toContain(`/activity/runs?limit=${limit}`));
    };

    await reach(200);
    await reach(500);

    await waitFor(() => expect(screen.getAllByTestId("run-card")).toHaveLength(500));
    expect(more()).not.toBeInTheDocument();
  });

  it("offers no further step when the history is shorter than a page", async () => {
    backend.runs = many(3);
    show();
    await waitFor(() => expect(screen.getAllByTestId("run-card")).toHaveLength(3));

    expect(screen.queryByRole("button", { name: vi.runFilters.more })).not.toBeInTheDocument();
  });

  it("offers a retry when the history cannot be read", async () => {
    vitest.stubGlobal("fetch", () => Promise.reject(new Error("offline")));
    show([fakeRun()]);

    const retry = await screen.findByRole("button", { name: vi.runFilters.retry });

    expect(screen.getByTestId("run-card")).toBeInTheDocument();
    expect(retry).toBeEnabled();
  });

  // The failure belongs to the query that failed; filed under the previous one, the log
  // waited on a load that had already given up.
  it("offers a retry when another agent's history cannot be read", async () => {
    backend.runs = many(2);
    show();
    await waitFor(() => expect(screen.getAllByTestId("run-card")).toHaveLength(2));
    vitest.stubGlobal("fetch", () => Promise.reject(new Error("offline")));

    await userEvent.click(chip(vi.runFilters.agent, coachAgent.name));

    expect(await screen.findByRole("button", { name: vi.runFilters.retry })).toBeEnabled();
    expect(screen.queryByText(vi.runFilters.loading)).not.toBeInTheDocument();
  });
});
