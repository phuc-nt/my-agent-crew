import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentInfo } from "../../api/types";
import type { ScheduleRow } from "../../hooks/agent-draft-checks";
import { vi } from "../../i18n/vi";
import { FakeBackend, fakeAgent } from "../../test/fake-backend";
import { SCHEDULES_RESTART_REASON } from "../../test/schedule-contract";
import { AgentEditor } from "./agent-editor";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  vitest.stubGlobal("fetch", backend.fetch);
});

function open(agent: AgentInfo = fakeAgent, focus?: string) {
  backend.agents = [agent];
  render(
    <AgentEditor
      agent={agent}
      agents={[agent]}
      tools={[]} mcpServers={[]}
      providers={["fake"]}
      onBack={() => {}}
      onChanged={() => {}}
      focus={focus}
    />,
  );
}

const brief: ScheduleRow = {
  id: "brief",
  name: "Bản tin sáng",
  cron: "0 7 * * *",
  every: null,
  prompt: "Tóm tắt",
  command: null,
  enabled: true,
  skills: ["core"],
};

/** An agent whose file already declares these rows. */
function declaring(...schedules: ScheduleRow[]): AgentInfo {
  return { ...fakeAgent, declared: { delegates: [], schedules } };
}

/** Adds a row and returns it, so each test fills only the boxes it is about. */
async function addRow() {
  await userEvent.click(screen.getByRole("button", { name: vi.editor.addSchedule }));
  const rows = screen.getAllByTestId("schedule-row");
  return within(rows[rows.length - 1]);
}

async function save() {
  await userEvent.click(screen.getByRole("button", { name: vi.editor.save }));
}

function sentProfile(): Record<string, unknown> {
  const patch = backend.requests.find((r) => r.method === "PATCH");
  expect(patch).toBeDefined();
  return (patch?.body as { profile: Record<string, unknown> }).profile;
}

describe("the schedules part of the agent editor", () => {
  // The parser refuses a row carrying the derived `kind`, or both a cron and an interval;
  // every new row the old form saved did one or the other.
  it("saves a new row as exactly one timing and one action, with no kind", async () => {
    open();
    const row = await addRow();
    await userEvent.type(row.getByLabelText(vi.editor.scheduleName), "Bản tin");
    await userEvent.type(row.getByLabelText(vi.editor.scheduleCron), "0 7 * * *");
    await userEvent.type(row.getByLabelText(vi.editor.schedulePrompt), "Tóm tắt tin");
    await save();

    await waitFor(() => expect(screen.getByTestId("restart-banner")).toBeInTheDocument());
    expect(sentProfile().schedules).toEqual([
      { name: "Bản tin", cron: "0 7 * * *", prompt: "Tóm tắt tin", enabled: true, skills: [] },
    ]);
    // The form restarts from what the server declared, the new row still in it.
    expect(within(screen.getAllByTestId("schedule-row")[0]).getByLabelText(vi.editor.scheduleName)).toHaveValue(
      "Bản tin",
    );
    expect(screen.getByText(vi.editor.clean)).toBeInTheDocument();
  });

  // The server says why in a whole sentence of its own. Taken for the name of a changed
  // key, that sentence once landed in the middle of another one, full stop and all, which
  // then asked for the restart a second time.
  it("tells the person why a restart is needed in the server's own sentence", async () => {
    open();
    const row = await addRow();
    await userEvent.type(row.getByLabelText(vi.editor.scheduleCron), "0 7 * * *");
    await userEvent.type(row.getByLabelText(vi.editor.schedulePrompt), "Tóm tắt tin");
    await save();

    const banner = within(await screen.findByTestId("restart-banner"));
    expect(banner.getByText("Cần khởi động lại")).toBeInTheDocument();
    expect(
      banner.getByText("Đã lưu. Thay đổi lịch chạy chỉ có hiệu lực sau khi khởi động lại máy chủ."),
    ).toBeInTheDocument();
  });

  // The clock keeps the jobs it started with, so a removed one runs on until the restart:
  // the banner is as true for it, and its sentence once spoke of a "new" schedule.
  it("asks for the restart after a schedule is removed, in words that fit a removal", async () => {
    open(declaring(brief));
    await userEvent.click(await screen.findByRole("button", { name: vi.editor.scheduleRemove("Bản tin sáng") }));
    await save();

    const banner = within(await screen.findByTestId("restart-banner"));
    expect(banner.getByText(`Đã lưu. ${SCHEDULES_RESTART_REASON}`)).toBeInTheDocument();
    expect(banner.queryByText(/mới/)).not.toBeInTheDocument();
    expect(sentProfile().schedules).toEqual([]);
  });

  it("keeps only the timing last chosen when the person switches back and forth", async () => {
    open();
    const row = await addRow();
    await userEvent.click(row.getByRole("button", { name: vi.editor.scheduleEvery }));
    await userEvent.type(row.getByLabelText(vi.editor.scheduleEvery), "30m");
    expect(row.queryByLabelText(vi.editor.scheduleCron)).not.toBeInTheDocument();
    await userEvent.type(row.getByLabelText(vi.editor.schedulePrompt), "Nhắc");
    await save();
    expect(sentProfile().schedules).toEqual([{ every: "30m", prompt: "Nhắc", enabled: true, skills: [] }]);

    backend.requests = [];
    await userEvent.click(row.getByRole("button", { name: vi.editor.scheduleCron }));
    expect(row.getByLabelText(vi.editor.scheduleCron)).toHaveValue("");
    await userEvent.type(row.getByLabelText(vi.editor.scheduleCron), "15 * * * *");
    await save();
    // The first save named the row the way the parser does, and the form kept that name.
    expect(sentProfile().schedules).toEqual([
      { id: "job-0", name: "job-0", cron: "15 * * * *", prompt: "Nhắc", enabled: true, skills: [] },
    ]);
  });

  it("swaps the prompt box for a monospace command box, and drops the skills with it", async () => {
    open();
    const row = await addRow();
    expect(row.getByLabelText(vi.editor.schedulePrompt)).not.toHaveClass("mono");
    expect(row.getByRole("group", { name: vi.jobSkills })).toBeInTheDocument();
    await userEvent.click(row.getByRole("button", { name: "core" }));

    await userEvent.click(row.getByRole("button", { name: vi.editor.scheduleCommand }));

    expect(row.getByRole("button", { name: vi.editor.scheduleCommand })).toHaveAttribute("aria-pressed", "true");
    expect(row.queryByLabelText(vi.editor.schedulePrompt)).not.toBeInTheDocument();
    expect(row.getByLabelText(vi.editor.scheduleCommand)).toHaveClass("mono");
    expect(row.queryByRole("group", { name: vi.jobSkills })).not.toBeInTheDocument();

    await userEvent.type(row.getByLabelText(vi.editor.scheduleCron), "0 3 * * *");
    await userEvent.type(row.getByLabelText(vi.editor.scheduleCommand), "echo hi");
    await save();
    expect(sentProfile().schedules).toEqual([{ cron: "0 3 * * *", command: "echo hi", enabled: true, skills: [] }]);
  });

  // The skills are attached to the conversation a prompt opens; left on a command they
  // were written to the file, listed on the job, and could no longer be seen or removed.
  it("takes an existing prompt job's skills off when it becomes a command", async () => {
    open(declaring(brief));
    const row = within(screen.getByTestId("schedule-row"));
    await userEvent.click(row.getByRole("button", { name: vi.editor.scheduleCommand }));
    await userEvent.type(row.getByLabelText(vi.editor.scheduleCommand), "echo hi");
    await save();

    expect(sentProfile().schedules).toEqual([
      { id: "brief", name: "Bản tin sáng", cron: "0 7 * * *", command: "echo hi", enabled: true, skills: [] },
    ]);
  });

  // A mis-tap on the other choice is one tap to undo, not a retyped prompt or cron.
  it("gives back what was written when a choice is switched away and back", async () => {
    open(declaring(brief));
    const row = within(screen.getByTestId("schedule-row"));
    const pick = (name: string) => userEvent.click(row.getByRole("button", { name }));

    await pick(vi.editor.scheduleCommand);
    await userEvent.type(row.getByLabelText(vi.editor.scheduleCommand), "echo hi");
    await pick(vi.editor.schedulePrompt);
    expect(row.getByLabelText(vi.editor.schedulePrompt)).toHaveValue("Tóm tắt");
    expect(row.getByRole("button", { name: "core" })).toHaveAttribute("aria-pressed", "true");
    await pick(vi.editor.scheduleCommand);
    expect(row.getByLabelText(vi.editor.scheduleCommand)).toHaveValue("echo hi");

    await pick(vi.editor.scheduleEvery);
    await userEvent.type(row.getByLabelText(vi.editor.scheduleEvery), "30m");
    await pick(vi.editor.scheduleCron);
    expect(row.getByLabelText(vi.editor.scheduleCron)).toHaveValue("0 7 * * *");
    await pick(vi.editor.scheduleEvery);
    expect(row.getByLabelText(vi.editor.scheduleEvery)).toHaveValue("30m");

    // Back where it started, the row is the file's row again: nothing to save.
    await pick(vi.editor.scheduleCron);
    await pick(vi.editor.schedulePrompt);
    expect(screen.getByText(vi.editor.clean)).toBeInTheDocument();
  });

  // A prompt written as a YAML block keeps its lines: a MEDIA: line joined onto the
  // sentence before it is no longer an attachment.
  it("edits a prompt of several lines without joining them", async () => {
    open(declaring({ ...brief, prompt: "Dòng một.\nMEDIA: a.png" }));
    const prompt = within(screen.getByTestId("schedule-row")).getByLabelText(vi.editor.schedulePrompt);
    expect(prompt).toHaveValue("Dòng một.\nMEDIA: a.png");

    await userEvent.type(prompt, "{Enter}Thêm dòng");
    await save();
    expect((sentProfile().schedules as ScheduleRow[])[0].prompt).toBe("Dòng một.\nMEDIA: a.png\nThêm dòng");
  });

  // The wait is written in agent.yaml and has no box in the form; the whole list goes back
  // on every save, so a row sent without it would lose it without anyone touching the row.
  it("keeps how long a row's approvals wait when another row is edited", async () => {
    open(declaring({ ...brief, approval_ttl_seconds: 7200 }, { ...brief, id: "evening", name: "Tối" }));

    const evening = within(screen.getAllByTestId("schedule-row")[1]).getByLabelText(vi.editor.scheduleName);
    await userEvent.type(evening, " muộn");
    await save();

    await waitFor(() => expect(screen.getByTestId("restart-banner")).toBeInTheDocument());
    const [kept, edited] = sentProfile().schedules as Record<string, unknown>[];
    expect(kept.approval_ttl_seconds).toBe(7200);
    expect(edited.name).toBe("Tối muộn");
    expect(edited).not.toHaveProperty("approval_ttl_seconds");
  });

  // Rows were keyed by position, so the focused Xoá button stayed where it was and now
  // belonged to the next schedule: a second press, or a double click, removed that one too.
  it("removes one schedule per press and hands focus to the one that moved up", async () => {
    const named = (name: string): ScheduleRow => ({ ...brief, id: name, name });
    open(declaring(named("Lịch a"), named("Lịch b"), named("Lịch c")));

    screen.getByRole("button", { name: vi.editor.scheduleRemove("Lịch a") }).focus();
    await userEvent.keyboard("{Enter}");
    const next = within(screen.getAllByTestId("schedule-row")[0]).getByLabelText(vi.editor.scheduleName);
    expect(next).toHaveValue("Lịch b");
    expect(next).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    expect(screen.getAllByTestId("schedule-row")).toHaveLength(2);

    // With no row after it, focus goes to adding one rather than back to the page.
    await userEvent.click(screen.getByRole("button", { name: vi.editor.scheduleRemove("Lịch c") }));
    expect(screen.getByRole("button", { name: vi.editor.addSchedule })).toHaveFocus();
    expect(screen.getAllByTestId("schedule-row")).toHaveLength(1);
  });

  it("says what the on-switch is on the row itself, and names a row not yet named", async () => {
    open(declaring(brief));
    const row = await addRow();
    expect(row.getByText(vi.jobEnabled)).toBeVisible();
    // The row's place in the list: "a new schedule" says nothing once there are two.
    expect(row.getByRole("checkbox", { name: vi.editor.scheduleEnabled(vi.editor.scheduleUnnamed(2)) })).toBeChecked();
    expect(row.getByRole("button", { name: vi.editor.scheduleRemove(vi.editor.scheduleUnnamed(2)) })).toBeEnabled();
  });

  // A new row is empty, not wrong: its boxes turn red when a save is tried, not on arrival.
  it("waits for a save before calling a new row's empty boxes wrong", async () => {
    open();
    const row = await addRow();
    expect(row.queryByText(vi.editor.cronInvalid)).not.toBeInTheDocument();
    expect(row.queryByText(vi.editor.promptMissing)).not.toBeInTheDocument();
    expect(screen.queryByTestId("save-held")).not.toBeInTheDocument();
    expect(row.getByText(vi.editor.scheduleCronHint)).toBeInTheDocument();

    await save();
    expect(row.getByText(vi.editor.cronInvalid)).toBeInTheDocument();
    expect(row.getByText(vi.editor.promptMissing)).toBeInTheDocument();
    // The error takes the hint's place rather than repeating it underneath.
    expect(row.queryByText(vi.editor.scheduleCronHint)).not.toBeInTheDocument();
    expect(screen.getByTestId("save-held")).toHaveTextContent(vi.editor.problemsHoldSave);
    expect(screen.getByRole("button", { name: vi.editor.save })).toBeDisabled();
    expect(backend.requests.some((r) => r.method === "PATCH")).toBe(false);

    // Filled in, the row saves.
    await userEvent.type(row.getByLabelText(vi.editor.scheduleCron), "0 7 * * *");
    await userEvent.type(row.getByLabelText(vi.editor.schedulePrompt), "Nhắc");
    await save();
    await waitFor(() => expect(screen.getByText(vi.editor.clean)).toBeInTheDocument());
  });

  // The server refuses hour 25 too, but in English and at the top of the page.
  it("names a cron value outside its field's range next to the box", async () => {
    open();
    const row = await addRow();
    await userEvent.type(row.getByLabelText(vi.editor.scheduleCron), "0 25 * * *");
    await userEvent.type(row.getByLabelText(vi.editor.schedulePrompt), "Nhắc");

    expect(row.getByText(vi.editor.cronInvalid)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: vi.editor.save })).toBeDisabled();
  });

  it("holds the save and names the box while a timing cannot be read", async () => {
    open();
    const row = await addRow();
    await userEvent.type(row.getByLabelText(vi.editor.scheduleCron), "0 7 * *");
    await userEvent.type(row.getByLabelText(vi.editor.schedulePrompt), "Nhắc");

    expect(row.getByText(vi.editor.cronInvalid)).toBeInTheDocument();
    expect(row.getByLabelText(vi.editor.scheduleCron)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByTestId("save-held")).toHaveTextContent(vi.editor.problemsHoldSave);
    expect(screen.getByRole("button", { name: vi.editor.save })).toBeDisabled();
    expect(backend.requests.some((r) => r.method === "PATCH")).toBe(false);
  });

  it("reads a timing back in words as it is typed, and only once it can be read", async () => {
    open();
    const row = await addRow();
    const cron = row.getByLabelText(vi.editor.scheduleCron);
    expect(row.getByText(vi.editor.scheduleCronHint)).toBeInTheDocument();

    await userEvent.type(cron, "0 7 * *");
    expect(row.queryByText(/^Tức là/)).not.toBeInTheDocument();
    await userEvent.type(cron, " 1-5");
    expect(row.getByText(vi.editor.scheduleReads("Thứ Hai–Thứ Sáu 07:00"))).toBeInTheDocument();

    await userEvent.click(row.getByRole("button", { name: vi.editor.scheduleEvery }));
    await userEvent.type(row.getByLabelText(vi.editor.scheduleEvery), "30s");
    // Under the one-minute floor: the error speaks, and no reading contradicts it.
    expect(row.getByText(vi.editor.everyInvalid)).toBeInTheDocument();
    expect(row.queryByText(/^Tức là/)).not.toBeInTheDocument();
    await userEvent.clear(row.getByLabelText(vi.editor.scheduleEvery));
    await userEvent.type(row.getByLabelText(vi.editor.scheduleEvery), "2h");
    expect(row.getByText(vi.editor.scheduleReads("Mỗi 2 giờ"))).toBeInTheDocument();
  });

  // The server numbers a row sent without an id by its place. With the first row gone the
  // kept one still carries job-1, and a new row at index 1 would be job-1 as well: the
  // scheduler keeps one job per id, so one of the two would never run.
  it("gives a new row a free id when its place is one a kept row already carries", async () => {
    const numbered = (at: number): ScheduleRow => ({ ...brief, id: `job-${at}`, name: `Lịch ${at}` });
    open(declaring(numbered(0), numbered(1)));
    await userEvent.click(screen.getByRole("button", { name: vi.editor.scheduleRemove("Lịch 0") }));
    const row = await addRow();
    await userEvent.type(row.getByLabelText(vi.editor.scheduleCron), "0 9 * * *");
    await userEvent.type(row.getByLabelText(vi.editor.schedulePrompt), "Nhắc");
    await save();

    await waitFor(() => expect(screen.getByText(vi.editor.clean)).toBeInTheDocument());
    const ids = (sentProfile().schedules as ScheduleRow[]).map((sent) => sent.id);
    expect(ids).toEqual(["job-1", "job-2"]);
    expect(screen.getAllByTestId("schedule-row")).toHaveLength(2);
  });

  it("holds the save and names the box while two rows are given the same id", async () => {
    open(declaring(brief));
    const row = await addRow();
    await userEvent.type(row.getByLabelText(vi.editor.scheduleId), "brief");
    await userEvent.type(row.getByLabelText(vi.editor.scheduleCron), "0 9 * * *");
    await userEvent.type(row.getByLabelText(vi.editor.schedulePrompt), "Nhắc");

    expect(row.getByText(vi.editor.scheduleIdTaken)).toBeInTheDocument();
    expect(row.getByLabelText(vi.editor.scheduleId)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("button", { name: vi.editor.save })).toBeDisabled();
    expect(backend.requests.some((r) => r.method === "PATCH")).toBe(false);
  });

  it("keeps the consolidation job's id for that job while consolidation is on", async () => {
    open({ ...declaring(brief), memory_consolidate: "0 3 * * *" });
    const row = within(screen.getByTestId("schedule-row"));
    await userEvent.clear(row.getByLabelText(vi.editor.scheduleId));
    await userEvent.type(row.getByLabelText(vi.editor.scheduleId), "memory-consolidate");
    expect(row.getByText(vi.editor.scheduleIdReserved)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: vi.editor.save })).toBeDisabled();

    // Consolidation off, the id is free to use.
    await userEvent.clear(screen.getByLabelText(vi.editor.memoryConsolidate));
    expect(row.queryByText(vi.editor.scheduleIdReserved)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: vi.editor.save })).toBeEnabled();
  });

  it("removes the consolidation cron from the file when the box is emptied", async () => {
    open({ ...fakeAgent, memory_consolidate: "0 3 * * *" });
    await userEvent.clear(screen.getByLabelText(vi.editor.memoryConsolidate));
    await save();

    await waitFor(() => expect(screen.getByText(vi.editor.clean)).toBeInTheDocument());
    expect(sentProfile()).toEqual({ memory_consolidate: null });
    expect(screen.getByLabelText(vi.editor.memoryConsolidate)).toHaveValue("");
  });

  it("brings the schedules into view when opened from the jobs list", () => {
    // jsdom has no scrolling, so the method is put in place for this test and taken away.
    const scroll = vitest.fn();
    const before = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = scroll;
    try {
      open(fakeAgent, "schedules");

      const heading = screen.getByRole("heading", { name: vi.editor.sectionSchedules });
      expect(heading).toHaveFocus();
      expect(scroll.mock.contexts).toContain(heading);
    } finally {
      Element.prototype.scrollIntoView = before;
    }
  });
});
