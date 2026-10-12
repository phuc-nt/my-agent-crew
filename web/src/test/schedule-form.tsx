// The schedule rows of the agent form, as a test fills them in and saves them.
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, vi as vitest } from "vitest";
import type { AgentInfo } from "../api/types";
import { AgentEditor } from "../components/agent-editor/agent-editor";
import type { ScheduleRow } from "../hooks/schedule-row-shape";
import { vi } from "../i18n/vi";
import { FakeBackend, fakeAgent } from "./fake-backend";

const t = vi.editor;

export const brief: ScheduleRow = { id: "brief", name: "Bản tin sáng", cron: "0 7 * * *", every: null, prompt: "Tóm tắt", command: null, script: null, then_prompt: null, enabled: true, skills: [] };
export const backup: ScheduleRow = { ...brief, id: "backup", name: "Sao lưu", prompt: null, command: "make backup" };
export const sync: ScheduleRow = { ...brief, id: "sync", name: "Đồng bộ đơn", prompt: null, script: "print(1)\n" };
/** A row the file leaves unnamed, as the server declares it: numbered by its place. */
export const placed = (row: ScheduleRow, at: number): ScheduleRow => ({ ...row, id: `job-${at}` });

export type Row = ReturnType<typeof within>;
/** The rows of one save, as they were sent. */
export type Sent = Record<string, unknown>[];

/** The form of one agent, on a back end of its own answering `fetch`. */
export function scheduleForm() {
  const backend = new FakeBackend();
  vitest.stubGlobal("fetch", backend.fetch);

  /** The editor on the agent as the crew list has it now: mounting it again is a reload. */
  const mount = () => {
    cleanup();
    const [agent] = backend.agents;
    render(<AgentEditor agent={agent} agents={[agent]} tools={[]} mcpServers={[]} providers={["fake"]} onBack={() => {}} onChanged={() => {}} />);
  };
  const rows = (): Row[] => screen.getAllByTestId("schedule-row").map((row) => within(row));
  const saves = (): Sent[] =>
    backend.requests.filter((asked) => asked.method === "PATCH").map((asked) => (asked.body as { profile: { schedules: Sent } }).profile.schedules);
  const pressSave = () => userEvent.click(screen.getByRole("button", { name: t.save }));

  return {
    backend,
    mount,
    rows,
    saves,
    pressSave,
    /** Opens the form on an agent whose file declares these rows. */
    open(...schedules: ScheduleRow[]) {
      const agent: AgentInfo = { ...fakeAgent, declared: { ...fakeAgent.declared, schedules } };
      backend.agents = [agent];
      mount();
    },
    /** What each row's id box holds. */
    ids: () => rows().map((row) => (idBox(row) as HTMLInputElement).value),
    /** Saves, and returns the rows sent once the server has taken them. */
    async saved(): Promise<Sent> {
      const before = saves().length;
      await pressSave();
      await waitFor(() => expect(saves()).toHaveLength(before + 1));
      await waitFor(() => expect(screen.getByRole("button", { name: t.save })).toBeDisabled());
      return saves()[before];
    },
    /** A row added at the end, named and timed, its id box left as it opens: empty. */
    async addRow(): Promise<Row> {
      await userEvent.click(screen.getByRole("button", { name: t.addSchedule }));
      const row = rows().at(-1)!;
      await userEvent.type(row.getByLabelText(t.scheduleName), "Việc mới");
      await userEvent.type(row.getByLabelText(t.scheduleCron), "40 6 * * *");
      return row;
    },
  };
}

export const idBox = (row: Row) => row.getByLabelText(t.scheduleId);
/** The line under a row's id box that says what the box is for. */
export const idHint = (row: Row) => (idBox(row).closest("label") as HTMLElement).querySelector(".field-hint")?.textContent;
/** Chooses what a row does: a prompt, a command or a script, by the choice's own label. */
export const pick = (row: Row, kind: string) => userEvent.click(within(row.getByRole("group", { name: t.scheduleAction })).getByRole("button", { name: kind }));
