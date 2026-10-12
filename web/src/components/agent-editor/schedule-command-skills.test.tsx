// A command opens no turn, so the form shows no skills on one. A file written by hand may
// list some on a command row all the same. They are the row's as the file has it: going to
// another kind and back leaves them where they were, and a save does not write them away.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentInfo } from "../../api/types";
import type { ScheduleRow } from "../../hooks/schedule-row-shape";
import { vi } from "../../i18n/vi";
import { FakeBackend, fakeAgent } from "../../test/fake-backend";
import { AgentEditor } from "./agent-editor";

const t = vi.editor;
const nightly: ScheduleRow = { id: "nightly", name: "Sao lưu", cron: "0 2 * * *", every: null, prompt: null, command: "make backup", script: null, then_prompt: null, enabled: true, skills: ["writer", "core"] };

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  vitest.stubGlobal("fetch", backend.fetch);
});

/** The editor on an agent whose file declares the command row, and the row. */
function open() {
  const agent: AgentInfo = { ...fakeAgent, declared: { ...fakeAgent.declared, schedules: [nightly] } };
  backend.agents = [agent];
  render(<AgentEditor agent={agent} agents={[agent]} tools={[]} mcpServers={[]} providers={["fake"]} onBack={() => {}} onChanged={() => {}} />);
  const row = within(screen.getByTestId("schedule-row"));
  const kinds = within(row.getByRole("group", { name: t.scheduleAction }));
  return {
    row,
    pick: (name: string) => userEvent.click(kinds.getByRole("button", { name })),
    box: (label: string) => row.getByLabelText(label),
    /** The skills shown as on, in the order the row shows them. */
    skills: () => within(row.getByRole("group", { name: vi.jobSkills })).getAllByRole("button", { pressed: true }).map((b) => b.textContent),
    skill: (name: string) => within(row.getByRole("group", { name: vi.jobSkills })).getByRole("button", { name }),
  };
}

/** Saves, and returns the one row that was sent once the server has answered. */
async function saved(): Promise<Record<string, unknown>> {
  await userEvent.click(screen.getByRole("button", { name: t.save }));
  await waitFor(() => expect(screen.getByTestId("restart-banner")).toBeInTheDocument());
  const patch = backend.requests.find((r) => r.method === "PATCH");
  return (patch?.body as { profile: { schedules: Record<string, unknown>[] } }).profile.schedules[0];
}

function nothingToSave() {
  expect(screen.getByText(t.clean)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: t.save })).toBeDisabled();
}

describe("the skills a command row lists in its file", () => {
  it.each([
    ["a prompt", [t.schedulePrompt]],
    ["a script", [t.scheduleScript]],
    ["a prompt, then a script", [t.schedulePrompt, t.scheduleScript]],
  ])("leave nothing to save once the row went to %s and came back", async (_name, way) => {
    const { pick, row, box } = open();
    nothingToSave();
    expect(row.queryByRole("group", { name: vi.jobSkills })).toBeNull();

    for (const kind of [...way, t.scheduleCommand]) await pick(kind);

    expect(box(t.scheduleCommand)).toHaveValue("make backup");
    nothingToSave();
  });

  it("are written as the file had them when the command's words change after a round trip", async () => {
    const { pick, box } = open();
    await pick(t.schedulePrompt);
    await pick(t.scheduleCommand);

    await userEvent.type(box(t.scheduleCommand), " --all");

    expect(await saved()).toEqual({ id: "nightly", name: "Sao lưu", cron: "0 2 * * *", command: "make backup --all", enabled: true, skills: ["writer", "core"] });
  });

  // The one place they can be seen: a row made a prompt shows them on, and saves what is left on.
  it("go on with the row to a prompt, where one taken off is saved off", async () => {
    const { pick, box, skills, skill } = open();

    await pick(t.schedulePrompt);
    expect(skills()).toEqual(["core", "writer"]);
    await userEvent.click(skill("core"));
    await userEvent.type(box(t.schedulePrompt), "Báo kết quả sao lưu");

    expect(await saved()).toEqual({ id: "nightly", name: "Sao lưu", cron: "0 2 * * *", prompt: "Báo kết quả sao lưu", enabled: true, skills: ["writer"] });
  });

  // Each kind keeps its own list: what was taken off the prompt was not taken off the command.
  it("are the command's own again after one was taken off on the prompt", async () => {
    const { pick, skills, skill } = open();
    await pick(t.schedulePrompt);
    await userEvent.click(skill("core"));

    await pick(t.scheduleCommand);
    nothingToSave();

    await pick(t.schedulePrompt);
    expect(skills()).toEqual(["writer"]);
  });
});
