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

const log = (streamed: RunInfo[] = []) => (
  <RecentRunsLog
    streamed={streamed}
    agents={[fakeAgent, coachAgent]}
    agentName={(id) => (id === "coach" ? "HLV" : "Agent")}
    onOpenConversation={() => undefined}
    onOpenRun={() => undefined}
    onBackToChat={() => undefined}
  />
);

function show(streamed: RunInfo[] = []) {
  return render(log(streamed));
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

  // The server's page holds runs still going too; they belong to the live list above,
  // and a copy here would show the same run twice on one screen.
  it("lists only runs that have finished", async () => {
    backend.runs = [
      fakeRun({ id: "going", status: "running", finished_at: null, title: "Đang làm" }),
      fakeRun({ id: "asking", status: "awaiting_approval", finished_at: null, title: "Chờ duyệt" }),
      fakeRun({ id: "over", status: "done", title: "Đã xong" }),
    ];
    show();

    expect(await screen.findByText(/Đã xong/)).toBeInTheDocument();
    expect(screen.getAllByTestId("run-card")).toHaveLength(1);
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

    await userEvent.click(chip(vi.runFilters.status, vi.runFilters.statuses.error));
    await userEvent.click(chip(vi.runFilters.source, "Lịch"));

    expect(screen.getAllByTestId("run-card")).toHaveLength(1);
    expect(screen.getByText(/Lỗi lịch/)).toBeInTheDocument();
    expect(runsAsked()).toHaveLength(asked);
  });

  it("says when nothing matches, and clears the chips on request", async () => {
    backend.runs = [fakeRun({ status: "done" })];
    show();
    await screen.findByTestId("run-card");

    await userEvent.click(chip(vi.runFilters.status, vi.runFilters.statuses.halted));
    expect(screen.getByText(vi.runFilters.none)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: vi.runFilters.clear }));

    expect(screen.getByTestId("run-card")).toBeInTheDocument();
  });

  it("remembers the chips for the next visit", async () => {
    backend.runs = [fakeRun({ status: "error" })];
    const { unmount } = show();
    await userEvent.click(await screen.findByRole("button", { name: vi.runFilters.statuses.error }));
    unmount();

    show();

    expect(chip(vi.runFilters.status, vi.runFilters.statuses.error)).toHaveAttribute("aria-pressed", "true");
  });

  // A private window, or a browser with site data blocked, has no storage to read.
  it("still filters where the browser refuses to remember anything", async () => {
    vitest.stubGlobal("localStorage", undefined);
    backend.runs = [fakeRun({ id: "x", status: "error" }), fakeRun({ id: "y", status: "done" })];
    show();
    await waitFor(() => expect(screen.getAllByTestId("run-card")).toHaveLength(2));

    await userEvent.click(chip(vi.runFilters.status, vi.runFilters.statuses.done));

    expect(screen.getAllByTestId("run-card")).toHaveLength(1);
  });

  it("reaches further back a step at a time and stops at the server's ceiling", async () => {
    backend.runs = many(600);
    show();
    // Found by text: a role query weighs every one of the hundreds of cards on screen,
    // which made this test slow enough to time out on a busy machine.
    const more = () => screen.queryByText(vi.showMore, { selector: "button" });
    // While a step loads the button says so and ignores a click, which would ask for nothing.
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

  // Judged by the step asked for, the button vanished the moment it was pressed: nothing
  // said a page was coming, and the focus of whoever pressed it fell to the page itself.
  it("keeps 'Xem thêm' in place and focused while the next page loads", async () => {
    backend.runs = many(250);
    let release = () => undefined as void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).includes("limit=200")) await gate;
      return backend.fetch(input, init);
    });
    show();
    const more = await screen.findByText(vi.showMore, { selector: "button" });

    more.focus();
    await userEvent.keyboard("{Enter}");

    expect(more).toHaveFocus();
    expect(more).toHaveAttribute("aria-disabled", "true");
    expect(more).toHaveTextContent(vi.runFilters.loadingMore);
    release();
    await waitFor(() => expect(screen.getAllByTestId("run-card")).toHaveLength(200));
    expect(more).toHaveFocus();
    expect(more).not.toHaveAttribute("aria-disabled", "true");
    expect(more).toHaveTextContent(vi.showMore);
  });

  // The last page takes the button with it, and the focus of whoever pressed it fell to
  // the top of the page, a long way from the runs that page had just brought.
  it("hands focus to the first run the last page brought", async () => {
    backend.runs = many(150);
    show();
    const more = await screen.findByText(vi.showMore, { selector: "button" });

    more.focus();
    await userEvent.keyboard("{Enter}");

    await waitFor(() => expect(screen.getAllByTestId("run-card")).toHaveLength(150));
    expect(more).not.toBeInTheDocument();
    const firstNew = screen.getAllByTestId("run-card")[100];
    await waitFor(() => expect(within(firstNew).getByRole("button")).toHaveFocus());
  });

  // A history exactly a page long looks as if it has more: the next page brings no run
  // that is not on show already, and there is no first new run to go to.
  it("hands focus to the last run when the next page brings nothing new", async () => {
    backend.runs = many(100);
    show();
    const more = await screen.findByText(vi.showMore, { selector: "button" });

    more.focus();
    await userEvent.keyboard("{Enter}");

    await waitFor(() => expect(more).not.toBeInTheDocument());
    const cards = screen.getAllByTestId("run-card");
    expect(cards).toHaveLength(100);
    await waitFor(() => expect(within(cards[99]).getByRole("button")).toHaveFocus());
  });

  // The hand-off is for the page that was asked for, once: a run streamed in later must
  // not pull the focus back from wherever the person has since put it.
  it("hands the focus on once, not again when a later run arrives", async () => {
    backend.runs = many(150);
    const view = show();
    const more = await screen.findByText(vi.showMore, { selector: "button" });
    more.focus();
    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(screen.getAllByTestId("run-card")).toHaveLength(150));
    const firstNew = within(screen.getAllByTestId("run-card")[100]);
    await waitFor(() => expect(firstNew.getByRole("button")).toHaveFocus());

    firstNew.getByRole("button").blur();
    const later = fakeRun({ id: "later", started_at: "2026-09-19T09:00:00Z", finished_at: "2026-09-19T09:00:05Z" });
    view.rerender(log([later]));

    await waitFor(() => expect(screen.getAllByTestId("run-card")).toHaveLength(151));
    expect(document.body).toHaveFocus();
  });

  it("hands focus to the retry when the next page cannot be read", async () => {
    backend.runs = many(150);
    vitest.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) =>
      String(input).includes("limit=200") ? Promise.reject(new Error("offline")) : backend.fetch(input, init),
    );
    show();
    const more = await screen.findByText(vi.showMore, { selector: "button" });

    more.focus();
    await userEvent.keyboard("{Enter}");

    const retry = await screen.findByText(vi.retry, { selector: "button" });
    expect(more).not.toBeInTheDocument();
    expect(screen.getAllByTestId("run-card")).toHaveLength(100);
    await waitFor(() => expect(retry).toHaveFocus());
  });

  // Pressing the retry takes it off the page, and the focus of whoever pressed it fell to
  // the top of the page, whether the page then came or failed again.
  it("keeps the focus through a retry that fails again, then hands it to the first run the page brought", async () => {
    backend.runs = many(150);
    let online = false;
    let failed = 0;
    vitest.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) => {
      if (online || !String(input).includes("limit=200")) return backend.fetch(input, init);
      failed += 1;
      return Promise.reject(new Error("offline"));
    });
    show();
    const more = await screen.findByText(vi.showMore, { selector: "button" });
    more.focus();
    await userEvent.keyboard("{Enter}");
    const retry = () => screen.getByText(vi.retry, { selector: "button" });
    await waitFor(() => expect(retry()).toHaveFocus());

    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(failed).toBe(2));
    await waitFor(() => expect(retry()).toHaveFocus());

    online = true;
    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(screen.getAllByTestId("run-card")).toHaveLength(150));
    const firstNew = screen.getAllByTestId("run-card")[100];
    await waitFor(() => expect(within(firstNew).getByRole("button")).toHaveFocus());
  });

  it("offers no further step when the history is shorter than a page", async () => {
    backend.runs = many(3);
    show();
    await waitFor(() => expect(screen.getAllByTestId("run-card")).toHaveLength(3));

    expect(screen.queryByRole("button", { name: vi.showMore })).not.toBeInTheDocument();
  });

  it("offers a retry when the history cannot be read", async () => {
    vitest.stubGlobal("fetch", () => Promise.reject(new Error("offline")));
    show([fakeRun()]);

    const retry = await screen.findByRole("button", { name: vi.retry });

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

    expect(await screen.findByRole("button", { name: vi.retry })).toBeEnabled();
    expect(screen.queryByText(vi.runFilters.loading)).not.toBeInTheDocument();
  });
});
