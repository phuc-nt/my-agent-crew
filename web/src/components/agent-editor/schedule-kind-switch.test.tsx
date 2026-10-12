import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentInfo } from "../../api/types";
import type { ScheduleRow } from "../../hooks/schedule-row-shape";
import { vi } from "../../i18n/vi";
import { FakeBackend, fakeAgent } from "../../test/fake-backend";
import { AgentEditor } from "./agent-editor";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  vitest.stubGlobal("fetch", backend.fetch);
});

const t = vi.editor;
const brief: ScheduleRow = { id: "brief", name: "Bản tin sáng", cron: "0 7 * * *", every: null, prompt: "Tóm tắt", command: null, script: null, then_prompt: null, enabled: true, skills: ["core"] };
const sync: ScheduleRow = { ...brief, id: "sync", name: "Đồng bộ đơn", prompt: null, script: "print(1)\n", then_prompt: "Tóm tắt đơn mới", skills: ["writer"] };
const backup: ScheduleRow = { ...brief, id: "backup", name: "Sao lưu", prompt: null, command: "make backup", skills: [] };
/** A row as a server older than script jobs declares it: neither script key at all. */
const { script: _script, then_prompt: _then, ...older } = brief;

/** The editor on an agent whose file declares this one row, and the row. */
function open(schedule: ScheduleRow) {
  const agent: AgentInfo = { ...fakeAgent, declared: { ...fakeAgent.declared, schedules: [schedule] } };
  backend.agents = [agent];
  render(<AgentEditor agent={agent} agents={[agent]} tools={[]} mcpServers={[]} providers={["fake"]} onBack={() => {}} onChanged={() => {}} />);
  const row = within(screen.getByTestId("schedule-row"));
  const kinds = within(row.getByRole("group", { name: t.scheduleAction }));
  return {
    row,
    pick: (name: string) => userEvent.click(kinds.getByRole("button", { name })),
    box: (label: string) => row.getByLabelText(label),
    skills: () => row.queryAllByRole("button", { pressed: true }).filter((b) => b.className === "chip").map((b) => b.textContent),
  };
}

/** Saves, and returns the one row that was sent once the server has answered. */
async function saved(): Promise<Record<string, unknown>> {
  await userEvent.click(screen.getByRole("button", { name: t.save }));
  await waitFor(() => expect(screen.getByTestId("schedule-live")).toBeInTheDocument());
  const patch = backend.requests.find((r) => r.method === "PATCH");
  return (patch?.body as { profile: { schedules: Record<string, unknown>[] } }).profile.schedules[0];
}

describe("switching what a schedule does", () => {
  // A prompt run as code, or code sent to the model as a prompt, is what a carried text
  // would be: each kind opens on its own words, or on an empty box.
  it("never carries one kind's words into another kind's box", async () => {
    const { pick, box, row } = open(brief);

    await pick(t.scheduleScript);
    expect(box(t.scheduleScript)).toHaveValue("");
    expect(box(t.scheduleThenPrompt)).toHaveValue("");
    expect(row.queryByLabelText(t.schedulePrompt)).toBeNull();

    await userEvent.type(box(t.scheduleScript), "print(2)");
    await userEvent.type(box(t.scheduleThenPrompt), "Báo kết quả");
    await pick(t.scheduleCommand);
    expect(box(t.scheduleCommand)).toHaveValue("");
    expect(row.queryByLabelText(t.scheduleScript)).toBeNull();
    expect(row.queryByLabelText(t.scheduleThenPrompt)).toBeNull();

    await userEvent.type(box(t.scheduleCommand), "make backup");
    await pick(t.schedulePrompt);
    expect(box(t.schedulePrompt)).toHaveValue("Tóm tắt");
  });

  it("gives each kind back what it held: its words, its prompt to follow, its skills", async () => {
    const { pick, box, skills } = open(sync);
    expect(skills()).toEqual(["writer"]);

    await pick(t.schedulePrompt);
    await userEvent.type(box(t.schedulePrompt), "Chào buổi sáng");
    // A prompt new to the row starts with no skills; the script's are not its own.
    expect(skills()).toEqual([]);
    await userEvent.click(screen.getByRole("button", { name: "core" }));
    await pick(t.scheduleCommand);
    await userEvent.type(box(t.scheduleCommand), "make backup");

    await pick(t.scheduleScript);
    expect(box(t.scheduleScript)).toHaveValue("print(1)\n");
    expect(box(t.scheduleThenPrompt)).toHaveValue("Tóm tắt đơn mới");
    expect(skills()).toEqual(["writer"]);
    await pick(t.schedulePrompt);
    expect(box(t.schedulePrompt)).toHaveValue("Chào buổi sáng");
    expect(skills()).toEqual(["core"]);
    await pick(t.scheduleCommand);
    expect(box(t.scheduleCommand)).toHaveValue("make backup");
  });

  it.each([
    ["a prompt", brief, t.schedulePrompt],
    ["a prompt from a server older than script jobs", older, t.schedulePrompt],
    ["a command", backup, t.scheduleCommand],
    ["a script", sync, t.scheduleScript],
  ])("leaves nothing to save once %s is switched round and back", async (_name, schedule, own) => {
    const { pick } = open(schedule);
    for (const kind of [t.schedulePrompt, t.scheduleCommand, t.scheduleScript, t.schedulePrompt, own]) await pick(kind);

    expect(screen.getByText(t.clean)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: t.save })).toBeDisabled();
  });

  // What the other kinds hold stays in the form, and none of it is written.
  it("saves only the kind chosen when the form is saved", async () => {
    const { pick, box } = open(brief);
    await pick(t.scheduleScript);
    await userEvent.type(box(t.scheduleScript), "print(2)");

    expect(await saved()).toEqual({ id: "brief", name: "Bản tin sáng", cron: "0 7 * * *", script: "print(2)", enabled: true, skills: [] });
    expect(backend.agents[0].declared.schedules[0]).toMatchObject({ prompt: null, command: null, script: "print(2)", then_prompt: null });
    // The row the server declares back is the row on the page.
    expect(box(t.scheduleScript)).toHaveValue("print(2)");
    expect(screen.getByRole("button", { name: t.save })).toBeDisabled();
  });

  it("saves a script made a prompt as a prompt, with no prompt to follow beside it", async () => {
    const { pick, box } = open(sync);
    await pick(t.schedulePrompt);
    await userEvent.type(box(t.schedulePrompt), "Chào buổi sáng");

    expect(await saved()).toEqual({ id: "sync", name: "Đồng bộ đơn", cron: "0 7 * * *", prompt: "Chào buổi sáng", enabled: true, skills: [] });
    expect(backend.agents[0].declared.schedules[0]).toMatchObject({ prompt: "Chào buổi sáng", script: null, then_prompt: null });
  });

  // Skills go with the turn a row opens. A script opens one only with a prompt to follow.
  it("offers a script its skills once it has a prompt to follow, and sends them", async () => {
    const { pick, box, row } = open(brief);
    await pick(t.scheduleScript);
    expect(row.queryByRole("group", { name: vi.jobSkills })).toBeNull();

    await userEvent.type(box(t.scheduleScript), "print(2)");
    await userEvent.type(box(t.scheduleThenPrompt), "Báo kết quả");
    await userEvent.click(within(row.getByRole("group", { name: vi.jobSkills })).getByRole("button", { name: "writer" }));

    expect(await saved()).toMatchObject({ script: "print(2)", then_prompt: "Báo kết quả", skills: ["writer"] });
  });

  it("drops the skills when a row becomes a command, which opens no turn", async () => {
    const { pick, box } = open(sync);
    await pick(t.scheduleCommand);
    await userEvent.type(box(t.scheduleCommand), "make backup");

    expect(await saved()).toEqual({ id: "sync", name: "Đồng bộ đơn", cron: "0 7 * * *", command: "make backup", enabled: true, skills: [] });
  });
});
