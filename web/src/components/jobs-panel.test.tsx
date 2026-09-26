import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi as vitest } from "vitest";
import type { JobInfo } from "../api/activity-types";
import { vi } from "../i18n/vi";
import { coachAgent } from "../test/fake-backend";
import { JobsPanel } from "./jobs-panel";

const name = (id: string) => (id === "coach" ? "HLV" : "Agent");
const brief: JobInfo = {
  ...coachAgent.schedules[0],
  id: "coach/brief",
  schedule_id: "brief",
  agent_id: "coach",
  next_run: null,
  last_run: null,
  running: false,
  paused: false,
};

describe("where the jobs list sends a person to change a schedule", () => {
  it("opens the agent's editor from the job's own edit button", async () => {
    const onEdit = vitest.fn();
    render(
      <JobsPanel jobs={[brief]} agentName={name} onRunNow={() => {}} onToggle={() => {}} onEditSchedules={onEdit} />,
    );

    const job = screen.getByTestId("job");
    await userEvent.click(within(job).getByRole("button", { name: vi.jobRow.editOf(brief.name) }));
    expect(onEdit).toHaveBeenCalledWith("coach");
  });

  // Schedules used to be added by hand in agent.yaml, and the empty list said so; the
  // editor adds them now, and the empty list is the place a person first looks.
  it("points an empty list at the crew, where schedules are added, not at a file", async () => {
    const onOpenCrew = vitest.fn();
    render(<JobsPanel jobs={[]} agentName={name} onRunNow={() => {}} onToggle={() => {}} onOpenCrew={onOpenCrew} />);

    expect(screen.getByText(vi.jobsEmpty)).not.toHaveTextContent("agent.yaml");
    await userEvent.click(screen.getByRole("button", { name: vi.jobRow.openCrew }));
    expect(onOpenCrew).toHaveBeenCalled();
  });

  it("tells a schedule switched off in its profile to be turned back on in the editor", () => {
    render(
      <JobsPanel
        jobs={[{ ...brief, enabled: false }]}
        agentName={name}
        onRunNow={() => {}}
        onToggle={() => {}}
        onEditSchedules={() => {}}
      />,
    );

    const toggle = within(screen.getByTestId("job")).getByRole("checkbox").closest("label");
    expect(toggle).toHaveAttribute("title", vi.jobDisabledInProfile);
    expect(vi.jobDisabledInProfile).not.toContain("agent.yaml");
    expect(vi.jobDisabledInProfile).toContain(vi.jobRow.edit);
  });
});
