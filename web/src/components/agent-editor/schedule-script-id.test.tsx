// A row the form sends without an id is numbered by the server, and that holds for a row
// that runs a script as for any other: nothing is stored under a script row's id that a
// prompt's or a command's does not have, so its id box may be left empty like theirs.
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

describe("a schedule and its id", () => {
  it.each([
    ["a script", t.scheduleScript, "print(2)", { script: "print(2)" }],
    ["a prompt", t.schedulePrompt, "Chào buổi sáng", { prompt: "Chào buổi sáng" }],
    ["a command", t.scheduleCommand, "make backup", { command: "make backup" }],
  ])("lets %s go without one, numbered by the server", async (_name, kind, words, action) => {
    form.open(brief);
    const row = await form.addRow();
    await pick(row, kind);
    await userEvent.type(row.getByLabelText(kind), words);

    const sent = await form.saved();

    expect(sent[1]).toEqual({ name: "Việc mới", cron: "40 6 * * *", ...action, enabled: true, skills: [] });
    expect(idBox(form.rows()[1])).not.toHaveAttribute("aria-invalid");
    expect(screen.queryByTestId("save-held")).toBeNull();
    expect(form.ids()).toEqual(["brief", "job-1"]);
    form.mount();
    expect(form.ids()).toEqual(["brief", "job-1"]);
  });

  it.each([
    ["emptied", ""],
    ["made nothing but spaces", "   "],
  ])("lets a script of the file be saved with its id %s", async (_name, typed) => {
    form.open(sync);
    const [row] = form.rows();
    await userEvent.clear(idBox(row));
    if (typed) await userEvent.type(idBox(row), typed);

    const sent = await form.saved();

    expect(sent[0]).toEqual({ name: "Đồng bộ đơn", cron: "0 7 * * *", script: "print(1)\n", enabled: true, skills: [] });
  });

  it("is told the same thing under its id box whatever it runs: the box may be left empty", async () => {
    form.open(brief, backup, sync);
    expect(form.rows().map(idHint)).toEqual([t.scheduleIdHint, t.scheduleIdHint, t.scheduleIdHint]);
    expect(t.scheduleIdHint).toContain("Bỏ trống");

    await pick(form.rows()[0], t.scheduleScript);
    await pick(form.rows()[2], t.schedulePrompt);
    expect(form.rows().map(idHint)).toEqual([t.scheduleIdHint, t.scheduleIdHint, t.scheduleIdHint]);
  });
});
