import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { JobInfo } from "../api/activity-types";
import { vi } from "../i18n/vi";
import { coachAgent } from "../test/fake-backend";
import { JobsPanel } from "./jobs-panel";

const name = (id: string) => (id === "coach" ? "HLV" : "Agent");
/** A prompt job as a server older than script jobs lists it: no `script`, no `then_prompt`. */
const brief: JobInfo = {
  ...coachAgent.schedules[0],
  id: "coach/brief",
  schedule_id: "brief",
  agent_id: "coach",
  next_run: null,
  last_run: null,
  running: false,
  paused: false,
  origin: "profile",
};

const SOURCE = 'orders = tools.workspace_read(path="orders.json")\nif orders:\n    print(len(orders), "đơn mới")';
const sync: JobInfo = {
  ...brief,
  id: "coach/sync",
  schedule_id: "sync",
  name: "Đồng bộ đơn",
  kind: "script",
  cron: "40 6 * * *",
  prompt: null,
  command: null,
  script: SOURCE,
  then_prompt: "Tóm tắt các đơn mới cho chủ",
  skills: [],
};
const backup: JobInfo = {
  ...brief,
  id: "coach/backup",
  schedule_id: "backup",
  name: "Sao lưu",
  kind: "command",
  prompt: null,
  command: "make backup",
  script: null,
  then_prompt: null,
  skills: [],
};

function show(...jobs: JobInfo[]) {
  const { unmount } = render(<JobsPanel jobs={jobs} agentName={name} onRunNow={() => {}} onToggle={() => {}} />);
  return { rows: screen.getAllByTestId("job"), unmount };
}

/** The line that says when a job runs and what kind of job it is. */
const timingLine = (row: HTMLElement, written: string) => within(row).getByText(written, { selector: "code" }).parentElement!;

describe("a job that runs a script, in the jobs list", () => {
  // Without a word of its own the row ended on "· " and read as a job of no kind at all.
  it("is named by its kind", () => {
    const { rows } = show(sync);
    expect(timingLine(rows[0], "40 6 * * *")).toHaveTextContent(new RegExp(` · ${vi.jobKindScript}$`));
    expect(vi.jobKindScript).not.toBe(vi.jobKindCommand);
    expect(vi.jobKindScript).not.toBe(vi.jobKindPrompt);
  });

  it("shows the script it runs as it was written, line breaks and all", () => {
    const { rows } = show(sync);
    const shown = within(rows[0]).getByTestId("job-script");
    // Read off the node, not through a matcher that folds the line breaks into spaces.
    expect(shown.querySelector("pre code")?.textContent).toBe(SOURCE);
  });

  it("shows the prompt its output is handed on with", () => {
    const { rows } = show(sync);
    expect(within(rows[0]).getByTestId("job-then-prompt")).toHaveTextContent(
      new RegExp(`^${vi.jobThenPrompt}: Tóm tắt các đơn mới cho chủ$`),
    );
  });

  // A script with no prompt to follow calls no model: a line promising one would be a lie.
  it("says nothing of a prompt when the script hands its output to no one", () => {
    for (const none of [{ then_prompt: null }, { then_prompt: undefined }, { then_prompt: "" }]) {
      const { rows, unmount } = show({ ...sync, ...none });
      expect(within(rows[0]).getByTestId("job-script")).toBeInTheDocument();
      expect(within(rows[0]).queryByTestId("job-then-prompt")).toBeNull();
      unmount();
    }
  });

  it("keeps each job's script on that job's row", () => {
    const { rows } = show(brief, sync, backup);
    expect(rows.map((row) => within(row).queryAllByTestId("job-script").length)).toEqual([0, 1, 0]);
    expect(rows.map((row) => within(row).queryAllByTestId("job-then-prompt").length)).toEqual([0, 1, 0]);
  });
});

describe("the jobs that run no script", () => {
  it("are named as before: a command job a command, a prompt job a prompt", () => {
    const { rows } = show(backup, brief);
    expect(timingLine(rows[0], "0 7 * * *")).toHaveTextContent(new RegExp(` · ${vi.jobKindCommand}$`));
    expect(timingLine(rows[1], "0 7 * * *")).toHaveTextContent(new RegExp(` · ${vi.jobKindPrompt}$`));
  });

  // The two keys arrive as null on every row a newer server lists, and not at all from an
  // older one: neither may add a line to a row that had none.
  it("draw the same row whether the script keys came as null or did not come", () => {
    const drawn = (job: JobInfo) => {
      const { rows, unmount } = show(job);
      const html = rows[0].innerHTML;
      unmount();
      return html;
    };
    const { script: _script, then_prompt: _then, ...older } = backup;

    expect(drawn(backup)).toBe(drawn(older));
    expect(drawn(backup)).not.toContain("job-script");
    // A prompt left on a row that runs no script is not this row's to show.
    expect(drawn({ ...backup, then_prompt: "Tóm tắt" })).toBe(drawn(older));
  });
});
