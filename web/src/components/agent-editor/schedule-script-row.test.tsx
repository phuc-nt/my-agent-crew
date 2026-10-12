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

const SOURCE = 'orders = tools.workspace_read(path="orders.json")\nif orders:\n    print(len(orders), "đơn mới")\n';
/** A script job as the file declares it: neither a prompt nor a command, both keys null. */
const sync: ScheduleRow = {
  id: "sync",
  name: "Đồng bộ đơn",
  cron: "40 6 * * *",
  every: null,
  prompt: null,
  command: null,
  script: SOURCE,
  then_prompt: "Tóm tắt các đơn mới cho chủ",
  enabled: true,
  skills: [],
};
const brief: ScheduleRow = {
  id: "brief",
  name: "Bản tin sáng",
  cron: "0 7 * * *",
  every: null,
  prompt: "Tóm tắt",
  command: null,
  script: null,
  then_prompt: null,
  enabled: true,
  skills: ["core"],
};
/** The script row exactly as the parser is to get it back. */
const SYNC_SENT = { id: "sync", name: "Đồng bộ đơn", cron: "40 6 * * *", script: SOURCE, then_prompt: "Tóm tắt các đơn mới cho chủ", enabled: true, skills: [] };

/** The editor on an agent whose file already declares these rows. */
function open(...schedules: ScheduleRow[]) {
  const agent: AgentInfo = { ...fakeAgent, declared: { ...fakeAgent.declared, schedules } };
  backend.agents = [agent];
  render(
    <AgentEditor agent={agent} agents={[agent]} tools={[]} mcpServers={[]} providers={["fake"]} onBack={() => {}} onChanged={() => {}} />,
  );
  return screen.getAllByTestId("schedule-row").map((row) => within(row));
}

/** Saves, waits for the server's answer, and returns the rows that were sent. */
async function saved(): Promise<Record<string, unknown>[]> {
  await userEvent.click(screen.getByRole("button", { name: vi.editor.save }));
  // Shown only once the save was taken: a refused row leaves an error in its place.
  await waitFor(() => expect(screen.getByTestId("restart-banner")).toBeInTheDocument());
  const patch = backend.requests.find((r) => r.method === "PATCH");
  return (patch?.body as { profile: { schedules: Record<string, unknown>[] } }).profile.schedules;
}

describe("a schedule that runs a script, in the agent editor", () => {
  // The whole list is sent on every save. A form that knew two actions sent this row with
  // neither, the parser refused the save, and no other row of the agent could be changed.
  it("goes back as it came when another row is edited", async () => {
    const [, other] = open(sync, brief);
    await userEvent.type(other.getByLabelText(vi.editor.scheduleName), " sớm");

    const [kept, edited] = await saved();

    expect(kept).toEqual(SYNC_SENT);
    expect(edited.name).toBe("Bản tin sáng sớm");
    // And an ordinary row gains nothing from the keys it was declared with as null.
    expect(edited).not.toHaveProperty("script");
    expect(edited).not.toHaveProperty("then_prompt");
    expect(backend.agents[0].declared.schedules[0]).toMatchObject({ script: SOURCE, then_prompt: sync.then_prompt, prompt: null, command: null });
  });

  it("keeps its script when its own name, timing and switch are changed", async () => {
    const [row] = open(sync, brief);
    await userEvent.type(row.getByLabelText(vi.editor.scheduleName), " sáng");
    await userEvent.click(within(row.getByRole("group", { name: vi.editor.scheduleTiming })).getByRole("button", { name: vi.editor.scheduleEvery }));
    await userEvent.type(row.getByLabelText(vi.editor.scheduleEvery), "6h");
    await userEvent.click(row.getByRole("checkbox", { name: vi.editor.scheduleEnabled("Đồng bộ đơn sáng") }));

    const [sent] = await saved();

    expect(sent).toEqual({ id: "sync", name: "Đồng bộ đơn sáng", every: "6h", script: SOURCE, then_prompt: sync.then_prompt, enabled: false, skills: [] });
  });

  // The row has no prompt and no command, which is what the checks hold a save for.
  it("is not held as a row with nothing to do", async () => {
    const [row, other] = open(sync, brief);
    expect(screen.getByRole("button", { name: vi.editor.save })).toBeDisabled();

    await userEvent.type(other.getByLabelText(vi.editor.scheduleName), " sớm");

    expect(screen.getByRole("button", { name: vi.editor.save })).toBeEnabled();
    expect(screen.queryByTestId("save-held")).toBeNull();
    expect(row.queryByText(vi.editor.promptMissing)).toBeNull();
    expect(row.queryByText(vi.editor.commandMissing)).toBeNull();
    // Its timing is still the form's to check.
    await userEvent.clear(row.getByLabelText(vi.editor.scheduleCron));
    await userEvent.type(row.getByLabelText(vi.editor.scheduleCron), "lúc 7 giờ");
    expect(row.getByText(vi.editor.cronInvalid)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: vi.editor.save })).toBeDisabled();
  });

  it("shows its kind chosen among the three, and its script and its prompt whole", () => {
    const [row] = open(sync);
    const kinds = within(row.getByRole("group", { name: vi.editor.scheduleAction })).getAllByRole("button");
    expect(kinds.map((kind) => [kind.textContent, kind.getAttribute("aria-pressed")])).toEqual([
      [vi.editor.schedulePrompt, "false"],
      [vi.editor.scheduleCommand, "false"],
      [vi.editor.scheduleScript, "true"],
    ]);
    expect(row.getByLabelText(vi.editor.scheduleScript)).toHaveValue(SOURCE);
    expect(row.getByLabelText(vi.editor.scheduleThenPrompt)).toHaveValue(sync.then_prompt);
    // One action, one box: the boxes of the two kinds it is not are not on the row.
    expect(row.queryByLabelText(vi.editor.schedulePrompt)).toBeNull();
    expect(row.queryByLabelText(vi.editor.scheduleCommand)).toBeNull();
  });

  it("is typed in where it stands, and what is typed is what is saved", async () => {
    const [row] = open(sync);
    for (const label of [vi.editor.scheduleScript, vi.editor.scheduleThenPrompt])
      expect((row.getByLabelText(label) as HTMLTextAreaElement).readOnly).toBe(false);
    // Nothing typed, nothing to save.
    expect(screen.getByRole("button", { name: vi.editor.save })).toBeDisabled();

    await userEvent.type(row.getByLabelText(vi.editor.scheduleScript), "print(1)");
    await userEvent.type(row.getByLabelText(vi.editor.scheduleThenPrompt), " nhé");
    const [sent] = await saved();

    const written = { script: `${SOURCE}print(1)`, then_prompt: `${sync.then_prompt} nhé` };
    expect(sent).toEqual({ ...SYNC_SENT, ...written });
    expect(backend.agents[0].declared.schedules[0]).toMatchObject({ ...written, prompt: null, command: null });
  });

  it("is on offer for every row, and a row the form adds starts as a prompt", async () => {
    const [, other] = open(sync, brief);
    const choice = (row: ReturnType<typeof within>) =>
      within(row.getByRole("group", { name: vi.editor.scheduleAction })).getAllByRole("button").map((b) => b.textContent);
    const three = [vi.editor.schedulePrompt, vi.editor.scheduleCommand, vi.editor.scheduleScript];
    expect(choice(other)).toEqual(three);

    await userEvent.click(screen.getByRole("button", { name: vi.editor.addSchedule }));
    const added = within(screen.getAllByTestId("schedule-row")[2]);
    expect(choice(added)).toEqual(three);
    expect(added.getByRole("button", { name: vi.editor.schedulePrompt })).toHaveAttribute("aria-pressed", "true");
    expect(added.queryByLabelText(vi.editor.scheduleScript)).toBeNull();
  });

  // `then_prompt` is allowed beside a script and optional there; a null is not a prompt.
  it("sends no prompt to follow for a script that has none", async () => {
    const [row, other] = open({ ...sync, then_prompt: null }, brief);
    // The box is there to be filled, and empty.
    expect(row.getByLabelText(vi.editor.scheduleThenPrompt)).toHaveValue("");
    await userEvent.type(other.getByLabelText(vi.editor.scheduleName), " sớm");

    const [kept] = await saved();

    const { then_prompt: _none, ...bare } = SYNC_SENT;
    expect(kept).toEqual(bare);
    expect(backend.agents[0].declared.schedules[0]).toMatchObject({ script: SOURCE, then_prompt: null });
    // What the server declares back is the row the form already holds: nothing left to save.
    expect(screen.getByRole("button", { name: vi.editor.save })).toBeDisabled();
  });

  it("can be removed like any other row", async () => {
    open(sync, brief);
    await userEvent.click(screen.getByRole("button", { name: vi.editor.scheduleRemove("Đồng bộ đơn") }));
    expect(screen.getAllByTestId("schedule-row")).toHaveLength(1);

    const sent = await saved();

    expect(sent.map((row) => row.id)).toEqual(["brief"]);
    expect(backend.agents[0].declared.schedules.map((row) => row.id)).toEqual(["brief"]);
  });
});
