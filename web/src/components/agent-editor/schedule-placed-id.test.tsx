// A row the file leaves unnamed is numbered by its place every time the server starts, and
// the server declares it under that number. What a script keeps is stored under the id, so
// the form hands the number back as the row's id: once the schedules are saved the file
// holds it, and the row is the same job wherever it stands in the list.
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { vi } from "../../i18n/vi";
import { backup, brief, idBox, placed, scheduleForm, sync } from "../../test/schedule-form";

const t = vi.editor;
let form: ReturnType<typeof scheduleForm>;

beforeEach(() => {
  form = scheduleForm();
});

describe("a script row the server numbered by its place", () => {
  it("leaves nothing to save, and nothing to fill in, when its agent is opened", () => {
    form.open(brief, placed(sync, 1));

    expect(screen.getByText(t.clean)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: t.save })).toBeDisabled();
    expect(form.ids()).toEqual(["brief", "job-1"]);
    expect(form.rows()[1].queryByText(t.scheduleIdMissing)).toBeNull();
    expect(idBox(form.rows()[1])).not.toHaveAttribute("aria-invalid");
  });

  // The file holds no id for it until then: what is sent for `schedules` is what is written.
  it("goes back under that id the next time the schedules are saved, with nothing typed in its row", async () => {
    form.open(brief, placed(sync, 1));
    await userEvent.type(form.rows()[0].getByLabelText(t.scheduleName), " sớm");

    const sent = await form.saved();

    expect(sent.map((row) => row.id)).toEqual(["brief", "job-1"]);
    expect(form.ids()).toEqual(["brief", "job-1"]);
  });

  it("keeps that id when a row above it goes, save after save", async () => {
    form.open(placed(brief, 0), placed(backup, 1), placed(sync, 2));
    await userEvent.click(screen.getByRole("button", { name: t.scheduleRemove("Bản tin sáng") }));

    expect((await form.saved()).map((row) => row.id)).toEqual(["job-1", "job-2"]);
    expect(form.ids()).toEqual(["job-1", "job-2"]);

    // No reload in between: the form goes on from the server's answer.
    await userEvent.click(screen.getByRole("button", { name: t.scheduleRemove("Sao lưu") }));

    expect((await form.saved()).map((row) => row.id)).toEqual(["job-2"]);
    expect(form.ids()).toEqual(["job-2"]);
    expect(form.backend.agents[0].declared.schedules.map((row) => [row.id, row.script])).toEqual([["job-2", "print(1)\n"]]);
  });
});
