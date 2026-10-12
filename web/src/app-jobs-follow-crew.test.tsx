// A saved schedule is live at once, so the jobs list a person goes back to has to be the
// one the scheduler now runs. The page read the list when it opened and after each run;
// an agent written, made, installed or removed changed the jobs without either, and the
// list went on showing what it had until the page was loaded again.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentInfo, JobInfo } from "./api/types";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, FakeEventSource, coachAgent, coderTemplate, fakeAgent } from "./test/fake-backend";

const t = vi.editor;
const brief = { id: "brief", name: "Bản tin sáng", cron: "0 7 * * *", every: null, prompt: "Tóm tắt", command: null, enabled: true, skills: [] };
/** An agent whose file declares one schedule, and the job the scheduler runs for it. */
const coach: AgentInfo = {
  ...coachAgent,
  name: "HLV",
  schedules: [{ ...brief, kind: "prompt" }],
  declared: { ...coachAgent.declared, schedules: [brief] },
};
const briefJob: JobInfo = {
  ...coach.schedules[0], id: "coach/brief", schedule_id: "brief", agent_id: "coach",
  next_run: null, last_run: null, running: false, paused: false, origin: "profile",
};

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  backend.agents = [fakeAgent, coach];
  backend.jobs = [briefJob];
  FakeEventSource.instances = [];
  vitest.stubGlobal("fetch", backend.fetch);
  vitest.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vitest.unstubAllGlobals();
  vitest.restoreAllMocks();
  window.location.hash = "";
});

const sent = () => backend.requests.map((r) => `${r.method} ${r.path}`);
const jobReads = () => sent().filter((r) => r === "GET /jobs").length;
/** Whether the jobs were asked for after the last request of this kind had been sent. */
const jobsReadAfter = (request: string) => {
  const at = sent().lastIndexOf(request);
  expect(at).toBeGreaterThanOrEqual(0);
  return sent().slice(at + 1).includes("GET /jobs");
};
/** Each row's heading: whose job it is, then the job's name. */
const rows = () => screen.getAllByTestId("job").map((row) => row.querySelector(".job-name")?.textContent);
const editor = () => within(screen.getByTestId("agent-editor"));

/** Opens the jobs list and, from the one row on it, the editor of the agent it belongs to. */
async function opensEditorFromJobs() {
  window.location.hash = "#/manage/jobs";
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: vi.jobRow.editOf("Bản tin sáng") }));
  await screen.findByTestId("agent-editor");
  await waitFor(() => expect(editor().getAllByTestId("schedule-row")).toHaveLength(1));
}

/** Opens the crew page, where an agent is made, installed and opened for editing. */
async function opensCrew() {
  window.location.hash = "#/manage/crew";
  render(<App />);
  await waitFor(() => expect(screen.getAllByTestId("crew-agent")).toHaveLength(2));
  await waitFor(() => expect(jobReads()).toBe(1));
}

describe("the jobs list, after an agent's schedules were saved", () => {
  it("has the schedule that was added, with no reload of the page", async () => {
    await opensEditorFromJobs();
    expect(jobReads()).toBe(1);

    await userEvent.click(editor().getByRole("button", { name: t.addSchedule }));
    const added = within(editor().getAllByTestId("schedule-row")[1]);
    await userEvent.type(added.getByLabelText(t.scheduleName), "Dọn rác");
    await userEvent.type(added.getByLabelText(t.scheduleCron), "0 9 * * *");
    await userEvent.type(added.getByLabelText(t.schedulePrompt), "Dọn");
    await userEvent.click(editor().getByRole("button", { name: t.save }));
    expect((await editor().findByTestId("schedule-live")).textContent).toBe(t.scheduleLive);

    // Read once more, for the save, and before the person has gone anywhere.
    await waitFor(() => expect(jobReads()).toBe(2));
    expect(jobsReadAfter("PATCH /agents/coach")).toBe(true);

    await userEvent.click(editor().getByRole("button", { name: vi.jobRow.back }));
    await waitFor(() => expect(rows()).toEqual(["HLV · Bản tin sáng", "HLV · Dọn rác"]));
    // Going back showed what the save had already brought: it asked for nothing again.
    expect(jobReads()).toBe(2);
  });

  it("no longer has the schedule that was removed", async () => {
    await opensEditorFromJobs();

    await userEvent.click(editor().getByRole("button", { name: t.scheduleRemove("Bản tin sáng") }));
    await userEvent.click(editor().getByRole("button", { name: t.save }));
    await editor().findByTestId("schedule-live");
    await waitFor(() => expect(jobReads()).toBe(2));

    await userEvent.click(editor().getByRole("button", { name: vi.jobRow.back }));
    expect(await screen.findByText(vi.jobsEmpty)).toBeInTheDocument();
    expect(screen.queryByTestId("job")).not.toBeInTheDocument();
  });

  // A key that moves no job still goes through the one path every save takes; what this
  // holds is that the list is left as it was, the row and its place both.
  it("keeps its rows after a save that changed no schedule", async () => {
    await opensEditorFromJobs();

    // A schedule's row has a box of the same label, so the agent's own is found by its section.
    const name = within(editor().getByTestId("section-identity")).getByLabelText(t.name);
    await userEvent.clear(name);
    await userEvent.type(name, "HLV mới");
    await userEvent.click(editor().getByRole("button", { name: t.save }));
    await waitFor(() => expect(editor().getByText(t.clean)).toBeInTheDocument());
    expect(editor().queryByTestId("schedule-live")).not.toBeInTheDocument();

    await userEvent.click(editor().getByRole("button", { name: vi.jobRow.back }));
    await waitFor(() => expect(rows()).toEqual(["HLV mới · Bản tin sáng"]));
  });
});

// These three change which jobs there are on the server alone: a template brings its
// schedules, and a removed agent takes its jobs with it. The fake keeps no jobs for them,
// so what is held here is that the list is asked for again once the server has answered.
describe("the jobs list, after the crew changed", () => {
  it("is read again when an agent is made", async () => {
    await opensCrew();

    await userEvent.click(screen.getByRole("button", { name: vi.crew.add }));
    const form = within(screen.getByTestId("add-agent"));
    await userEvent.type(form.getByLabelText(vi.crew.addId), "scribe");
    await userEvent.click(form.getByRole("button", { name: vi.crew.create }));
    await screen.findByTestId("agent-editor");

    await waitFor(() => expect(jobReads()).toBe(2));
    expect(jobsReadAfter("POST /agents")).toBe(true);
  });

  it("is read again when a template is installed", async () => {
    backend.templates = [coderTemplate];
    await opensCrew();

    await userEvent.click(await screen.findByRole("button", { name: vi.crew.install }));
    expect(await screen.findByText(vi.crew.installed(["coder"]))).toBeInTheDocument();

    expect(jobReads()).toBe(2);
    expect(jobsReadAfter("POST /agents/install")).toBe(true);
    // The agent is in the crew that is running, and nothing asks for a restart.
    expect(screen.queryByText(vi.crew.needsRestart)).not.toBeInTheDocument();
  });

  it("is read again when an agent is removed", async () => {
    await opensCrew();
    await userEvent.click(within(screen.getAllByTestId("crew-agent")[1]).getByRole("button", { name: vi.crew.edit }));

    const removal = within(await screen.findByTestId("delete-agent"));
    await userEvent.type(removal.getByRole("textbox", { name: t.deleteTitle }), "coach");
    await userEvent.click(removal.getByRole("button", { name: t.deleteConfirm }));
    await waitFor(() => expect(screen.queryByTestId("agent-editor")).not.toBeInTheDocument());

    await waitFor(() => expect(jobReads()).toBe(2));
    expect(jobsReadAfter("DELETE /agents/coach")).toBe(true);
  });
});
