// A script row's prompt to follow belongs to the script kind alone, and an empty one is no
// prompt at all. Typing one and taking it back, either way, leaves the row as the file has
// it: the form has nothing to save, and a save would write nothing the person did not mean.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentInfo } from "../../api/types";
import type { ScheduleRow } from "../../hooks/schedule-row-shape";
import { vi } from "../../i18n/vi";
import { FakeBackend, fakeAgent } from "../../test/fake-backend";
import { AgentEditor } from "./agent-editor";

const t = vi.editor;
const brief: ScheduleRow = { id: "brief", name: "Bản tin sáng", cron: "0 7 * * *", every: null, prompt: "Tóm tắt", command: null, script: null, then_prompt: null, enabled: true, skills: ["core"] };
/** A script that tells nobody: the file gives it no prompt to follow. */
const quiet: ScheduleRow = { ...brief, id: "sync", name: "Đồng bộ đơn", prompt: null, script: "print(1)\n", skills: [] };

beforeEach(() => {
  vitest.stubGlobal("fetch", new FakeBackend().fetch);
});

/** The editor on an agent whose file declares this one row, and the row. */
function open(schedule: ScheduleRow) {
  const agent: AgentInfo = { ...fakeAgent, declared: { ...fakeAgent.declared, schedules: [schedule] } };
  render(<AgentEditor agent={agent} agents={[agent]} tools={[]} mcpServers={[]} providers={["fake"]} onBack={() => {}} onChanged={() => {}} />);
  const row = within(screen.getByTestId("schedule-row"));
  const kinds = within(row.getByRole("group", { name: t.scheduleAction }));
  return { pick: (name: string) => userEvent.click(kinds.getByRole("button", { name })), box: (label: string) => row.getByLabelText(label) };
}

function nothingToSave() {
  expect(screen.getByText(t.clean)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: t.save })).toBeDisabled();
}

describe("a prompt to follow that was typed and taken back", () => {
  it("does not stay on a prompt row that was a script for a moment", async () => {
    const { pick, box } = open(brief);

    await pick(t.scheduleScript);
    await userEvent.type(box(t.scheduleThenPrompt), "Báo kết quả");
    expect(screen.getByRole("button", { name: t.save })).toBeEnabled();
    await pick(t.schedulePrompt);

    expect(box(t.schedulePrompt)).toHaveValue("Tóm tắt");
    nothingToSave();
  });

  it("is no prompt once its box is emptied, on a script that had none", async () => {
    const { box } = open(quiet);

    await userEvent.type(box(t.scheduleThenPrompt), "Báo kết quả");
    expect(screen.getByRole("button", { name: t.save })).toBeEnabled();
    await userEvent.clear(box(t.scheduleThenPrompt));

    expect(box(t.scheduleThenPrompt)).toHaveValue("");
    nothingToSave();
  });
});
