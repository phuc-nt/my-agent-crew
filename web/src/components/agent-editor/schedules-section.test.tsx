import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentInfo } from "../../api/types";
import { vi } from "../../i18n/vi";
import { FakeBackend, fakeAgent } from "../../test/fake-backend";
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
      tools={[]}
      providers={["fake"]}
      onBack={() => {}}
      onChanged={() => {}}
      focus={focus}
    />,
  );
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
    expect(row.getByRole("group", { name: vi.editor.scheduleSkills })).toBeInTheDocument();

    await userEvent.click(row.getByRole("button", { name: vi.editor.scheduleCommand }));

    expect(row.getByRole("button", { name: vi.editor.scheduleCommand })).toHaveAttribute("aria-pressed", "true");
    expect(row.queryByLabelText(vi.editor.schedulePrompt)).not.toBeInTheDocument();
    expect(row.getByLabelText(vi.editor.scheduleCommand)).toHaveClass("mono");
    expect(row.queryByRole("group", { name: vi.editor.scheduleSkills })).not.toBeInTheDocument();

    await userEvent.type(row.getByLabelText(vi.editor.scheduleCron), "0 3 * * *");
    await userEvent.type(row.getByLabelText(vi.editor.scheduleCommand), "echo hi");
    await save();
    expect(sentProfile().schedules).toEqual([{ cron: "0 3 * * *", command: "echo hi", enabled: true, skills: [] }]);
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
