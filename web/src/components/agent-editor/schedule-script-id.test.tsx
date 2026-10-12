// What a script job keeps is stored under its schedule's id (`job:<id>`), and a row the
// file leaves unnamed is numbered by its place every time the server starts: `job-1` is
// the second row, whichever row that is by then. So the form does not let a row that runs a
// script go to the file without an id.
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { vi } from "../../i18n/vi";
import { backup, brief, idBox, idHint, pick, scheduleForm, sync } from "../../test/schedule-form";

const t = vi.editor;
let form: ReturnType<typeof scheduleForm>;

beforeEach(() => {
  form = scheduleForm();
});

describe("a schedule that runs a script and has no id", () => {
  it("is not saved: the save is held, and its id box says why once a save is tried", async () => {
    form.open(brief);
    const row = await form.addRow();
    await pick(row, t.scheduleScript);
    await userEvent.type(row.getByLabelText(t.scheduleScript), "print(2)");

    // A row just made a script is not wrong yet: nothing is said until a save is tried.
    expect(row.queryByText(t.scheduleIdMissing)).toBeNull();
    expect(idBox(row)).not.toHaveAttribute("aria-invalid");
    expect(screen.getByRole("button", { name: t.save })).toBeEnabled();
    await form.pressSave();

    expect(form.saves()).toEqual([]);
    expect(idBox(row)).toHaveAttribute("aria-invalid", "true");
    expect(idBox(row)).toHaveAccessibleDescription(t.scheduleIdMissing);
    expect(screen.getByTestId("save-held")).toHaveTextContent(t.problemsHoldSave);
    expect(screen.getByRole("button", { name: t.save })).toBeDisabled();
    for (const reason of ["script giữ lại", "theo mã"]) expect(t.scheduleIdMissing).toContain(reason);

    await userEvent.type(idBox(row), "orders");
    expect(row.queryByText(t.scheduleIdMissing)).toBeNull();
    expect(screen.queryByTestId("save-held")).toBeNull();
    const sent = await form.saved();

    expect(sent[1]).toEqual({ id: "orders", name: "Việc mới", cron: "40 6 * * *", script: "print(2)", enabled: true, skills: [] });
    expect(form.ids()).toEqual(["brief", "orders"]);
    form.mount();
    expect(form.ids()).toEqual(["brief", "orders"]);
  });

  // However the row came to run a script: the kind it has when it is saved is what counts.
  it.each([
    ["a new row filled in as a prompt", t.schedulePrompt, "Chào buổi sáng"],
    ["a new row filled in as a command", t.scheduleCommand, "make backup"],
  ])("is held when it is %s and then made a script", async (_name, kind, words) => {
    form.open(brief);
    const row = await form.addRow();
    await pick(row, kind);
    await userEvent.type(row.getByLabelText(kind), words);
    await pick(row, t.scheduleScript);
    await userEvent.type(row.getByLabelText(t.scheduleScript), "print(2)");
    await form.pressSave();

    expect(form.saves()).toEqual([]);
    expect(idBox(row)).toHaveAccessibleDescription(t.scheduleIdMissing);
  });

  it.each([
    ["a script of the file whose id was emptied", sync, false],
    ["a prompt of the file, its id emptied, made a script", brief, true],
    ["a command of the file, its id emptied, made a script", backup, true],
  ])("is held when it is %s", async (_name, schedule, switched) => {
    form.open(schedule);
    const [row] = form.rows();
    await userEvent.clear(idBox(row));
    if (switched) {
      await pick(row, t.scheduleScript);
      await userEvent.type(row.getByLabelText(t.scheduleScript), "print(2)");
    }
    await form.pressSave();

    expect(form.saves()).toEqual([]);
    expect(idBox(row)).toHaveAccessibleDescription(t.scheduleIdMissing);
  });

  // An id of spaces is not sent, so the server would number the row by its place just the same.
  it("is one whose id box holds nothing but spaces", async () => {
    form.open(sync);
    const [row] = form.rows();
    await userEvent.clear(idBox(row));
    await userEvent.type(idBox(row), "   ");
    await form.pressSave();

    expect(form.saves()).toEqual([]);
    expect(idBox(row)).toHaveAccessibleDescription(t.scheduleIdMissing);
  });

  it("is told under its id box what the id is for, where a row of another kind is told it may be left empty", async () => {
    form.open(brief, backup, sync);
    expect(form.rows().map(idHint)).toEqual([t.scheduleIdHint, t.scheduleIdHint, t.scheduleIdHintScript]);
    expect(t.scheduleIdHintScript).not.toContain("Bỏ trống");
    for (const reason of ["script giữ lại", "theo mã"]) expect(t.scheduleIdHintScript).toContain(reason);

    // The hint goes with the kind the row is now.
    await pick(form.rows()[0], t.scheduleScript);
    await pick(form.rows()[2], t.schedulePrompt);
    expect(form.rows().map(idHint)).toEqual([t.scheduleIdHintScript, t.scheduleIdHint, t.scheduleIdHint]);
  });
});

describe("a schedule of another kind and its id", () => {
  it.each([
    ["a prompt", t.schedulePrompt, "Chào buổi sáng", { prompt: "Chào buổi sáng" }],
    ["a command", t.scheduleCommand, "make backup", { command: "make backup" }],
  ])("lets %s go without one, numbered by the server as before", async (_name, kind, words, action) => {
    form.open(brief);
    const row = await form.addRow();
    await pick(row, kind);
    await userEvent.type(row.getByLabelText(kind), words);

    const sent = await form.saved();

    expect(sent[1]).toEqual({ name: "Việc mới", cron: "40 6 * * *", ...action, enabled: true, skills: [] });
    expect(form.rows()[1].queryByText(t.scheduleIdMissing)).toBeNull();
    expect(form.ids()).toEqual(["brief", "job-1"]);
    form.mount();
    expect(form.ids()).toEqual(["brief", "job-1"]);
  });

  // A script switched away from is not what the row runs: its empty id holds nothing.
  it("lets a row go without one once it is no longer a script", async () => {
    form.open(brief);
    const row = await form.addRow();
    await pick(row, t.scheduleScript);
    await form.pressSave();
    expect(idBox(row)).toHaveAccessibleDescription(t.scheduleIdMissing);

    await pick(row, t.schedulePrompt);
    await userEvent.type(row.getByLabelText(t.schedulePrompt), "Chào buổi sáng");
    expect(row.queryByText(t.scheduleIdMissing)).toBeNull();

    expect((await form.saved())[1]).toEqual({ name: "Việc mới", cron: "40 6 * * *", prompt: "Chào buổi sáng", enabled: true, skills: [] });
  });
});

