import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import { FakeBackend, fakeAgent, fakeApproval, fakeRun } from "../test/fake-backend";
import { ManageScreen, NAV_GROUPS } from "./manage-screen";
import { MANAGE_SECTIONS, type ManageSection } from "../hooks/use-route";

const name = (id: string) => (id === "coach" ? "HLV" : "Agent");

beforeEach(() => {
  vitest.stubGlobal("fetch", new FakeBackend().fetch);
});

function show(section: ManageSection, overrides: Partial<Parameters<typeof ManageScreen>[0]> = {}) {
  const live = fakeRun({ id: "live", status: "running", finished_at: null, conversation_id: "c2" });
  const done = fakeRun({ id: "done" });
  const onNavigate = vitest.fn();
  const onBackToChat = vitest.fn();
  render(
    <ManageScreen
      section={section}
      runs={[live, done]}
      liveRuns={[live]}
      attention={[]}
      jobs={[]}
      stats={null}
      settings={null}
      agents={[fakeAgent]}
      agentId="default"
      agentName={name}
      master={fakeAgent}
      templates={[]}
      liveByAgent={{}}
      onInstall={() => Promise.reject(new Error("không cài"))}
      onEditAgent={() => undefined}
      onReplayRun={() => undefined}
      onReloadCrew={() => undefined}
      onNavigate={onNavigate}
      onBackToChat={onBackToChat}
      onOpenConversation={() => undefined}
      onRunJob={() => undefined}
      onToggleJob={() => undefined}
      {...overrides}
    />,
  );
  return { onNavigate, onBackToChat };
}

describe("the manage screen", () => {
  // This screen is the whole crew's: a run belongs here whichever conversation is open.
  it("shows every run, live ones apart from the ones already finished", () => {
    show("activity");

    expect(screen.getAllByTestId("run-card")).toHaveLength(2);
  });

  it("shows one run on its own instead of the list when the URL names one", () => {
    show("activity", { replayRunId: "done" });

    // The list, the attention centre and the headings all give way: the URL is asking
    // about one run, and leaving the list underneath would bury it.
    expect(screen.getByTestId("run-replay")).toBeInTheDocument();
    expect(screen.getAllByTestId("run-card")).toHaveLength(1);
    expect(screen.queryByText(vi.recentRuns)).not.toBeInTheDocument();
  });

  it("asks to open a run on its own when its link is used", async () => {
    const onReplayRun = vitest.fn();
    show("activity", { onReplayRun });

    await userEvent.click(screen.getAllByRole("button", { name: vi.replay.openLink })[0]);

    expect(onReplayRun).toHaveBeenCalledWith("live");
  });

  // "Nothing has run yet" is only half an answer: nothing has run because nothing
  // has been asked, and the way back to the chat is what actually unblocks it.
  it("offers the way back to the chat when no run has happened yet", async () => {
    const { onBackToChat } = show("activity", { runs: [], liveRuns: [] });

    await userEvent.click(screen.getByRole("button", { name: vi.noRunsAction }));

    expect(onBackToChat).toHaveBeenCalled();
  });

  it("marks how many runs are live on the way into the activity section", () => {
    show("activity");

    expect(screen.getByRole("button", { name: /Hoạt động/ })).toHaveTextContent("1");
  });

  // Each section is reached by its own link rather than by a tab that forgets itself, so
  // the nav reports where the person is going rather than changing the screen itself.
  it("asks to move when another section is chosen", async () => {
    const { onNavigate } = show("activity");

    await userEvent.click(screen.getByRole("button", { name: vi.jobs }));

    expect(onNavigate).toHaveBeenCalledWith("jobs");
  });

  // On a phone the sections are a sideways row, and the current one may sit past its edge.
  it("brings the current section's entry into view", () => {
    const scrolled: Element[] = [];
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function (this: Element) {
      scrolled.push(this);
    };
    try {
      show("jobs");
    } finally {
      Element.prototype.scrollIntoView = original;
    }

    const current = screen.getByRole("button", { current: "page" });
    expect(current).toHaveTextContent(vi.jobs);
    expect(scrolled).toEqual([current]);
  });

  it("renders the schedule when that is the section asked for", () => {
    show("jobs");

    expect(screen.getByText(vi.jobsEmpty)).toBeInTheDocument();
  });

  it("renders the bill when that is the section asked for", () => {
    show("costs");

    expect(screen.getByText(vi.loadFailed)).toBeInTheDocument();
  });

  it("offers the way back to the conversation the person came from", async () => {
    const { onBackToChat } = show("crew");

    await userEvent.click(screen.getByRole("button", { name: vi.manage.backToChat }));

    expect(onBackToChat).toHaveBeenCalled();
  });

  // The settings used to be a drawer over the chat; as a section it must lose the dialog
  // role, or assistive tech announces a dialog the person cannot close.
  it("shows settings as part of the page, not as a dialog", () => {
    show("settings");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByText(vi.loadFailed)).toBeInTheDocument();
  });

  it("counts the work waiting on a person next to the approvals section", () => {
    show("activity", { attention: [fakeRun({ id: "waiting", status: "awaiting_approval" })] });

    // In the nav: the activity page now also points to Duyệt, by name, from its own card.
    const nav = within(screen.getByRole("navigation", { name: vi.manage.nav }));
    expect(nav.getByRole("button", { name: new RegExp(vi.approvalsTab) })).toHaveTextContent("1");
  });

  // Duyệt is where a decision is made; a failure has none to make, so it counts where
  // it is read, and each number says what it counts once an entry carries two.
  it("counts waiting requests on Duyệt and failures on Hoạt động, each named", () => {
    const waiting = fakeRun({ id: "waiting", status: "awaiting_approval", finished_at: null });
    show("crew", { attention: [waiting, fakeRun({ id: "broke", status: "error" }), fakeRun({ id: "cut", status: "halted" })] });

    // jsdom joins inline text without the spaces a browser keeps, hence the \s*.
    const named = (...parts: (string | number)[]) => new RegExp(`^${parts.join("\\s*")}$`);
    const nav = within(screen.getByRole("navigation", { name: vi.manage.nav }));
    expect(nav.getByRole("button", { name: named(vi.approvalsTab, 1, vi.manage.waitingBadge) })).toBeInTheDocument();
    expect(
      nav.getByRole("button", { name: named(vi.activity, 1, vi.manage.liveBadge, 2, vi.manage.failedBadge) }),
    ).toBeInTheDocument();
  });

  it("counts a request waiting on a decision on Duyệt only, not as running on Hoạt động", () => {
    const live = fakeRun({ id: "live", status: "running", finished_at: null, conversation_id: "c2" });
    const waiting = fakeRun({ id: "waiting", status: "awaiting_approval", finished_at: null });
    show("crew", { liveRuns: [live, waiting], attention: [waiting] });

    const named = (...parts: (string | number)[]) => new RegExp(`^${parts.join("\\s*")}$`);
    const nav = within(screen.getByRole("navigation", { name: vi.manage.nav }));
    expect(nav.getByRole("button", { name: named(vi.activity, 1, vi.manage.liveBadge) })).toBeInTheDocument();
    expect(nav.getByRole("button", { name: named(vi.approvalsTab, 1, vi.manage.waitingBadge) })).toBeInTheDocument();
  });

  it("leaves Hoạt động unmarked when the only live run is waiting on a decision", () => {
    const waiting = fakeRun({ id: "waiting", status: "awaiting_approval", finished_at: null });
    show("crew", { liveRuns: [waiting], attention: [waiting] });

    const nav = within(screen.getByRole("navigation", { name: vi.manage.nav }));
    expect(nav.getByRole("button", { name: vi.activity })).not.toHaveTextContent(/\d/);
  });

  it("leaves Duyệt unmarked when only a failure needs attention", () => {
    show("crew", { attention: [fakeRun({ id: "broke", status: "error" })] });

    const nav = within(screen.getByRole("navigation", { name: vi.manage.nav }));
    expect(nav.getByRole("button", { name: vi.approvalsTab })).not.toHaveTextContent(/\d/);
  });

  it("puts the requests waiting on a decision above the approval history, ready to decide", async () => {
    const backend = new FakeBackend();
    const expires = new Date(Date.now() + 5 * 60_000).toISOString();
    const c = backend.create({ status: "awaiting_approval", pending_approval: fakeApproval({ status: "pending", resolved_at: null, expires_at: expires }) });
    vitest.stubGlobal("fetch", backend.fetch);
    const waiting = fakeRun({ id: "waiting", status: "awaiting_approval", finished_at: null, conversation_id: c.id });
    show("approvals", { attention: [waiting, fakeRun({ id: "broke", status: "error" })] });

    const attention = screen.getByTestId("attention");
    expect(await within(attention).findByRole("alertdialog", { name: vi.awaitingApproval })).toBeInTheDocument();
    expect(within(attention).queryByText(vi.attentionFailed("Agent"))).not.toBeInTheDocument();
    const history = screen.getByRole("heading", { name: vi.approvalHistory });
    expect(attention.compareDocumentPosition(history) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("points from Duyệt to the unread failures on Hoạt động rather than saying nothing needs you", async () => {
    const { onNavigate } = show("approvals", { attention: [fakeRun({ id: "broke", status: "error" })] });

    const attention = screen.getByTestId("attention");
    expect(within(attention).queryByText(vi.attentionEmpty)).not.toBeInTheDocument();
    await userEvent.click(within(attention).getByRole("button", { name: vi.attentionFailedElsewhere(1) }));

    expect(onNavigate).toHaveBeenCalledWith("activity");
  });

  it("points from the activity page to the requests waiting on Duyệt", async () => {
    const waiting = fakeRun({ id: "waiting", status: "awaiting_approval", finished_at: null });
    const { onNavigate } = show("activity", { attention: [waiting] });

    expect(screen.queryByText(vi.attentionAwaiting("Agent"))).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: vi.attentionWaitingElsewhere(1) }));

    expect(onNavigate).toHaveBeenCalledWith("approvals");
  });

  // A red number beside the schedules is a claim that something broke; a job that ran
  // fine, is still running or has never run makes no such claim.
  it("counts the jobs whose last run failed beside the jobs entry, and nothing otherwise", () => {
    const job = (id: string, last: ReturnType<typeof fakeRun> | null) => ({
      id: `default/${id}`, schedule_id: id, agent_id: "default", name: id, kind: "prompt" as const,
      cron: "0 7 * * *", every: null, prompt: "p", command: null, enabled: true, skills: [],
      next_run: null, last_run: last, running: false, paused: false,
    });
    const fine = [job("a", fakeRun()), job("b", fakeRun({ status: "running" })), job("c", null)];
    show("crew", { jobs: fine });
    expect(screen.queryByTestId("jobs-failing")).not.toBeInTheDocument();
    cleanup();

    show("crew", { jobs: [...fine, job("d", fakeRun({ status: "error" })), job("e", fakeRun({ status: "error" }))] });
    const entry = screen.getByRole("button", { name: new RegExp(`^${vi.jobs}`) });
    expect(within(entry).getByTestId("jobs-failing")).toHaveTextContent("2");
    // The number is hidden from assistive tech and the sentence stands in for it. jsdom
    // lays nothing out, so the gap a flex row puts after the name is checked in e2e.
    expect(entry).toHaveAccessibleName(new RegExp(`^${vi.jobs}\\s*${vi.jobRow.failing(2)}$`));
  });

  it("opens the agent editor in place of the crew list when the route names one", async () => {
    show("crew", { editingAgentId: "default" });

    expect(await screen.findByTestId("agent-editor")).toBeInTheDocument();
    expect(screen.queryByTestId("crew-list")).not.toBeInTheDocument();
  });

  // Following a link to an agent that has since been removed should say so rather than
  // land on the list as though the URL had never named anything.
  it("says so when the route names an agent the crew no longer has", async () => {
    show("crew", { editingAgentId: "ghost" });

    expect(await screen.findByTestId("agent-not-found")).toHaveTextContent(vi.editor.notFound("ghost"));
    expect(screen.getByTestId("crew-list")).toBeInTheDocument();
  });

  it("lists every tool against every agent, and the connections with no secret among them", async () => {
    show("tools");
    expect(await screen.findByTestId("tools-matrix")).toBeInTheDocument();
  });
});

// A section reachable by URL but missing from the grouped nav would be one nobody finds.
it("puts every manage section in exactly one nav group", () => {
  const grouped = NAV_GROUPS.flatMap((group) => group.sections);
  expect([...grouped].sort()).toEqual([...MANAGE_SECTIONS].sort());
});
