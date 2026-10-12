import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentInfo } from "../../api/types";
import type { ScheduleRow } from "../../hooks/schedule-row-shape";
import { vi } from "../../i18n/vi";
import { FakeBackend, fakeAgent } from "../../test/fake-backend";
import { AgentEditor } from "./agent-editor";

const brief: ScheduleRow = { id: "brief", name: "Bản tin sáng", cron: "0 7 * * *", every: null, prompt: "Tóm tắt", command: null, script: null, then_prompt: null, enabled: true, skills: [] };
const sync: ScheduleRow = { ...brief, id: "sync", name: "Đồng bộ đơn", prompt: null, script: "print(1)\n" };
const backup: ScheduleRow = { ...brief, id: "backup", name: "Sao lưu", prompt: null, command: "make backup" };
const agent: AgentInfo = { ...fakeAgent, memory_consolidate: "0 3 * * *", declared: { ...fakeAgent.declared, schedules: [brief, sync, backup] } };

// jsdom has no scrolling, so the method is put in place for these tests and taken away.
const scroll = vitest.fn();
const before = Element.prototype.scrollIntoView;

beforeEach(() => {
  vitest.stubGlobal("fetch", new FakeBackend().fetch);
  scroll.mockClear();
  Element.prototype.scrollIntoView = scroll;
});

afterEach(() => {
  Element.prototype.scrollIntoView = before;
});

/** The editor as the jobs list opens it for this job's "edit schedule". */
function openFrom(job: string | undefined) {
  render(
    <AgentEditor agent={agent} agents={[agent]} tools={[]} mcpServers={[]} providers={["fake"]} onBack={() => {}} onChanged={() => {}} focus="schedules" fromJob={job} />,
  );
  return screen.getAllByTestId("schedule-row");
}

const heading = () => screen.getByRole("heading", { name: vi.editor.sectionSchedules });
/** The rows a script can hand focus to: only the one the person was sent to. */
const focusable = (rows: HTMLElement[]) => rows.filter((row) => row.hasAttribute("tabindex"));

describe("the editor, opened from a job's edit link", () => {
  // The section is far down the form and may hold many rows: the one whose link was
  // pressed is what comes into view, not the heading above them all.
  it("lands on the row of that job, among the others", async () => {
    const rows = openFrom("default/sync");

    await waitFor(() => expect(rows[1]).toHaveFocus());
    expect(scroll.mock.contexts).toEqual([rows[1]]);
    expect(scroll).toHaveBeenCalledWith({ block: "start" });
    expect(focusable(rows)).toEqual([rows[1]]);
    expect(rows[1]).toHaveAttribute("tabindex", "-1");
  });

  it("says the way back leads to the jobs list", () => {
    openFrom("default/sync");
    expect(screen.getByRole("button", { name: vi.jobRow.back })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: vi.editor.back })).toBeNull();
  });

  it.each([
    ["the memory pass, which is no row of the list", "default/memory-consolidate"],
    ["a schedule the file no longer has", "default/gone"],
    ["a job of another agent that shares a row's id", "coach/sync"],
    ["a job id that names no schedule", "default/"],
  ])("lands on the section's heading for %s", async (_what, job) => {
    const rows = openFrom(job);

    await waitFor(() => expect(heading()).toHaveFocus());
    expect(scroll.mock.contexts).toEqual([heading()]);
    expect(focusable(rows)).toEqual([]);
  });

  it("lands on the heading when no job sent the person there, and says the plain way back", async () => {
    const rows = openFrom(undefined);

    await waitFor(() => expect(heading()).toHaveFocus());
    expect(focusable(rows)).toEqual([]);
    expect(screen.getByRole("button", { name: vi.editor.back })).toBeInTheDocument();
  });

  // The mark follows the row, not its place: with the row above it gone, the row that
  // moved up is still the one, and a row given the same id afterwards is not.
  it("keeps to the row it landed on as the list around it changes", async () => {
    const rows = openFrom("default/sync");
    await waitFor(() => expect(rows[1]).toHaveFocus());

    await userEvent.click(screen.getByRole("button", { name: vi.editor.scheduleRemove("Bản tin sáng") }));
    const left = screen.getAllByTestId("schedule-row");
    expect(left).toEqual([rows[1], rows[2]]);
    expect(focusable(left)).toEqual([rows[1]]);

    await userEvent.click(screen.getByRole("button", { name: vi.editor.scheduleRemove("Đồng bộ đơn") }));
    await userEvent.click(screen.getByRole("button", { name: vi.editor.addSchedule }));
    const added = screen.getAllByTestId("schedule-row");
    await userEvent.type(added[1].querySelector("input.mono") as HTMLElement, "sync");
    expect(focusable(screen.getAllByTestId("schedule-row"))).toEqual([]);
  });
});
