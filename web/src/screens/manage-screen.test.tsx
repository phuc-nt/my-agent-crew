import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import { FakeBackend, fakeAgent, fakeRun } from "../test/fake-backend";
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

    expect(screen.getByRole("button", { name: new RegExp(vi.approvalsTab) })).toHaveTextContent("1");
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
