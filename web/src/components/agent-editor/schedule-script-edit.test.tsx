import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
const sync: ScheduleRow = { id: "sync", name: "Đồng bộ đơn", cron: "40 6 * * *", every: null, prompt: null, command: null, script: "print(1)\n", then_prompt: "Tóm tắt đơn mới", enabled: true, skills: [] };

/** The editor on this agent, and its schedule rows. */
function open(agent: AgentInfo = fakeAgent) {
  backend.agents = [agent];
  render(<AgentEditor agent={agent} agents={[agent]} tools={[]} mcpServers={[]} providers={["fake"]} onBack={() => {}} onChanged={() => {}} />);
  return screen.queryAllByTestId("schedule-row").map((row) => within(row));
}
const declaring = (...schedules: ScheduleRow[]): AgentInfo => ({ ...fakeAgent, declared: { ...fakeAgent.declared, schedules } });

/** Adds a row, names and times it, and makes it one that runs a script. It is given an id:
 *  what a script keeps is stored under it, and the form saves no script row without one. */
async function addScriptRow() {
  await userEvent.click(screen.getByRole("button", { name: t.addSchedule }));
  const row = within(screen.getAllByTestId("schedule-row").at(-1) as HTMLElement);
  await userEvent.type(row.getByLabelText(t.scheduleId), "orders");
  await userEvent.type(row.getByLabelText(t.scheduleName), "Đồng bộ");
  await userEvent.type(row.getByLabelText(t.scheduleCron), "40 6 * * *");
  await userEvent.click(row.getByRole("button", { name: t.scheduleScript }));
  return row;
}

const save = () => userEvent.click(screen.getByRole("button", { name: t.save }));
const sent = () => {
  const patch = backend.requests.find((r) => r.method === "PATCH");
  return (patch?.body as { profile: { schedules: Record<string, unknown>[] } } | undefined)?.profile.schedules;
};
/** The elements a control is described by, in the order it names them. */
const describedBy = (control: HTMLElement) =>
  (control.getAttribute("aria-describedby") ?? "").split(" ").filter(Boolean).map((id) => document.getElementById(id)?.textContent);

describe("a schedule's script, written in the form", () => {
  it("makes a new row that runs a script, sent as the parser takes it", async () => {
    open();
    const row = await addScriptRow();
    await userEvent.type(row.getByLabelText(t.scheduleScript), "if True:{enter}    print(1)");
    await save();

    await waitFor(() => expect(screen.getByTestId("schedule-live")).toBeInTheDocument());
    expect(sent()).toEqual([{ id: "orders", name: "Đồng bộ", cron: "40 6 * * *", script: "if True:\n    print(1)", enabled: true, skills: [] }]);
    expect(backend.agents[0].declared.schedules[0]).toMatchObject({ id: "orders", prompt: null, command: null, then_prompt: null });
    expect(row.getByLabelText(t.scheduleScript)).toHaveValue("if True:\n    print(1)");
    expect(screen.getByRole("button", { name: t.save })).toBeDisabled();
  });

  // Python reads the indentation: a tab pasted in, the spaces before a line and the last
  // line break all go to the file and come back as they were.
  it("keeps a pasted tab, leading spaces and the last line break through a save and a reopen", async () => {
    const source = "for order in orders:\n\tif order.new:\n\t    print(order.id)\n\n";
    open();
    const row = await addScriptRow();
    await userEvent.click(row.getByLabelText(t.scheduleScript));
    await userEvent.paste(source);
    expect(row.getByLabelText(t.scheduleScript)).toHaveValue(source);
    await save();

    await waitFor(() => expect(backend.agents[0].declared.schedules[0]?.script).toBe(source));
    cleanup();
    const [reopened] = open(backend.agents[0]);
    expect(reopened.getByLabelText(t.scheduleScript)).toHaveValue(source);
    expect(screen.getByRole("button", { name: t.save })).toBeDisabled();
  });

  // A box that takes Tab for itself is one a keyboard cannot leave.
  it("lets Tab leave the script box, both ways, and puts no tab in the script", async () => {
    const [row] = open(declaring(sync));
    const script = row.getByLabelText(t.scheduleScript);
    await userEvent.click(script);
    await userEvent.tab();
    await waitFor(() => expect(row.getByLabelText(t.scheduleThenPrompt)).toHaveFocus());
    await userEvent.tab({ shift: true });
    await waitFor(() => expect(script).toHaveFocus());
    await userEvent.tab({ shift: true });
    await waitFor(() => expect(row.getByRole("button", { name: t.scheduleScript })).toHaveFocus());
    expect(script).toHaveValue("print(1)\n");
    expect(t.scheduleScriptHint).toContain("Tab");
  });

  it("ties each box to its hint, and the script to what is wrong with it", async () => {
    open();
    const row = await addScriptRow();
    const script = row.getByLabelText(t.scheduleScript);
    expect(describedBy(script)).toEqual([t.scheduleScriptHint]);
    expect(script).not.toHaveAttribute("aria-invalid");
    expect(describedBy(row.getByLabelText(t.scheduleThenPrompt))).toEqual([t.scheduleThenPromptHint]);
    for (const said of ["Telegram", "không ai được báo"]) expect(t.scheduleThenPromptHint).toContain(said);

    // Empty is not wrong until a save is tried; then it is named, and nothing is sent.
    expect(row.queryByText(t.scriptMissing)).toBeNull();
    await save();
    expect(describedBy(script)).toEqual([t.scheduleScriptHint, t.scriptMissing]);
    expect(script).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByTestId("save-held")).toHaveTextContent(t.problemsHoldSave);
    expect(sent()).toBeUndefined();
  });

  it("holds the save for a script over the bound, at once, and lets it go when cut back", async () => {
    const [row] = open(declaring(sync));
    const script = row.getByLabelText(t.scheduleScript);
    fireEvent.change(script, { target: { value: "#".repeat(20_001) } });
    expect(row.getByText(t.scriptTooLong(20_000))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: t.save })).toBeDisabled();

    fireEvent.change(script, { target: { value: "#".repeat(20_000) } });
    expect(row.queryByText(t.scriptTooLong(20_000))).toBeNull();
    expect(screen.getByRole("button", { name: t.save })).toBeEnabled();
  });

  it("takes the prompt to follow out of the file when its box is emptied", async () => {
    const [row] = open(declaring(sync));
    await userEvent.clear(row.getByLabelText(t.scheduleThenPrompt));
    await save();

    await waitFor(() => expect(screen.getByTestId("schedule-live")).toBeInTheDocument());
    expect(sent()).toEqual([{ id: "sync", name: "Đồng bộ đơn", cron: "40 6 * * *", script: "print(1)\n", enabled: true, skills: [] }]);
    expect(backend.agents[0].declared.schedules[0].then_prompt).toBeNull();
    expect(screen.getByRole("button", { name: t.save })).toBeDisabled();
  });

  // Whether Python reads the script is the server's to say, and it says it on save.
  it("shows the server's own words when it refuses the script, and keeps what was typed", async () => {
    const refusal = "agent default: schedule sync: script: Dòng 2: `import` không dùng được trong script.";
    const [row] = open(declaring(sync));
    await userEvent.type(row.getByLabelText(t.scheduleScript), "import os");
    backend.refuseEdit = refusal;
    await save();

    expect(await screen.findByText(t.saveFailed(refusal))).toBeInTheDocument();
    expect(row.getByLabelText(t.scheduleScript)).toHaveValue("print(1)\nimport os");
    expect(screen.getByRole("button", { name: t.save })).toBeEnabled();
  });

  // A script is longer than its box: read-only, it still scrolls and can be copied from.
  it("is read, not typed in, on an agent the form cannot change", async () => {
    const [row] = open({ ...declaring(sync), editable: false });
    for (const label of [t.scheduleScript, t.scheduleThenPrompt]) {
      const box = row.getByLabelText(label) as HTMLTextAreaElement;
      const before = box.value;
      expect(box.readOnly).toBe(true);
      expect(box).toBeEnabled();
      await userEvent.type(box, "print(2)");
      expect(box).toHaveValue(before);
    }
    for (const kind of within(row.getByRole("group", { name: t.scheduleAction })).getAllByRole("button")) expect(kind).toBeDisabled();
  });
});
