// The agent's own say over the machine's desktop, in its editor: `computer` sent as the word
// "on" or "off" and never as a switch, the applications it may act in as a list (an emptied
// box sends an empty one), the server's refusal shown beside the control it is about with
// what was typed kept, and no control at all for an agent of a server that knows no desktop.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi as vitest } from "vitest";
import type { AgentInfo } from "../../api/types";
import { vi } from "../../i18n/vi";
import { FakeBackend, fakeAgent } from "../../test/fake-backend";
import { AgentEditor } from "./agent-editor";
import { appLines } from "./desktop-controls";

const t = vi.editor;
const d = vi.desktop.editor;
let backend: FakeBackend;

function open(agent: AgentInfo) {
  backend = new FakeBackend();
  backend.agents = [agent];
  vitest.stubGlobal("fetch", backend.fetch);
  render(<AgentEditor agent={agent} agents={[agent]} tools={[]} mcpServers={[]} providers={[]} onBack={() => {}} onChanged={() => {}} />);
}

const off: AgentInfo = { ...fakeAgent, computer: "off", computer_apps: [] };
const on: AgentInfo = { ...fakeAgent, computer: "on", computer_apps: ["Notes", "com.apple.TextEdit"] };

/** The agent as a server older than the desktop reports it: with neither key. */
const older: AgentInfo = fakeAgent;

const section = () => within(screen.getByTestId("section-tools"));
const controls = () => within(screen.getByTestId("desktop-controls"));
const mode = () => section().getByRole("combobox", { name: d.mode }) as HTMLSelectElement;
const apps = () => section().getByRole("textbox", { name: d.apps }) as HTMLTextAreaElement;
const noApps = () => expect(section().queryByRole("textbox", { name: d.apps })).not.toBeInTheDocument();
const saveButton = () => screen.getByRole("button", { name: t.save });
const save = () => userEvent.click(saveButton());
const saved = () => waitFor(() => expect(screen.getByText(t.clean)).toBeInTheDocument());
const patches = () => backend.requests.filter((r) => r.method === "PATCH").map((r) => r.body);

describe("whether an agent may use the machine's desktop", () => {
  it("offers off and on under words of their own, opening on what the file says", () => {
    open(on);

    expect(within(mode()).getAllByRole("option").map((o) => [(o as HTMLOptionElement).value, o.textContent])).toEqual([
      ["off", "Tắt"],
      ["on", "Bật"],
    ]);
    expect(mode()).toHaveValue("on");
    expect(apps()).toHaveValue("Notes\ncom.apple.TextEdit");
    expect(section().getByRole("heading", { name: vi.desktop.title })).toBeInTheDocument();
    // A turn already running keeps the tools it began with: a save is for the next one.
    expect(section().getByText(d.sectionHint)).toBeInTheDocument();
    expect(d.sectionHint).toBe("Có hiệu lực từ lượt kế tiếp sau khi lưu, không cần khởi động lại.");
  });

  it("says one line for the mode chosen, naming the four tools and the gate when on", async () => {
    open(off);
    expect(mode()).toHaveAccessibleDescription(d.modeHint.off);

    await userEvent.selectOptions(mode(), "on");

    expect(mode()).toHaveAccessibleDescription(d.modeHint.on);
    for (const name of ["computer_state", "computer_screenshot", "computer_observe", "computer_act"]) expect(d.modeHint.on).toContain(name);
    expect(d.modeHint.on).toContain("kể cả khi hội thoại tự chủ");
  });

  it("saves on as the word itself, never as a switch", async () => {
    open(off);

    await userEvent.selectOptions(mode(), "on");
    await save();

    await saved();
    expect(patches()).toEqual([{ profile: { computer: "on" } }]);
    expect(typeof (patches()[0] as { profile: { computer: unknown } }).profile.computer).toBe("string");
    expect(backend.agents[0].computer).toBe("on");
    expect(mode()).toHaveValue("on");
  });

  it("saves off as the word alone, and leaves the applications in the file", async () => {
    open(on);

    await userEvent.selectOptions(mode(), "off");
    await save();

    await saved();
    expect(patches()).toEqual([{ profile: { computer: "off" } }]);
    expect(backend.agents[0]).toMatchObject({ computer: "off", computer_apps: ["Notes", "com.apple.TextEdit"] });
  });

  it("says the helper and its permissions are the machine owner's, and why the tools have no tick", () => {
    open(off);

    expect(controls().getByTestId("desktop-helper-note")).toHaveTextContent(d.helperNote);
    expect(d.helperNote).toContain("chủ máy");
    expect(section().getByText(vi.desktop.outsideList)).toBeInTheDocument();
  });

  it("cannot be changed on an agent that is not edited here", () => {
    open({ ...on, editable: false });

    expect(mode()).toBeDisabled();
    expect(apps()).toBeDisabled();
  });
});

describe("the applications an agent may act in", () => {
  it("have no box while the agent is off, and one once it is on", async () => {
    open(off);
    noApps();

    await userEvent.selectOptions(mode(), "on");
    expect(apps()).toHaveValue("");
    expect(apps()).toHaveAccessibleDescription(d.appsHint);
    // An empty list is an agent that only looks, and the line under the box says so.
    expect(d.appsHint).toContain("chỉ nhìn màn hình");
  });

  it("are saved trimmed, once each, with blank lines dropped", async () => {
    open({ ...on, computer_apps: [] });

    await userEvent.type(apps(), "  Notes  {Enter}{Enter}com.apple.TextEdit{Enter}Notes");
    expect(apps()).toHaveValue("  Notes  \n\ncom.apple.TextEdit\nNotes");
    await save();

    await saved();
    expect(patches()).toEqual([{ profile: { computer_apps: ["Notes", "com.apple.TextEdit"] } }]);
  });

  it("are sent as an empty list once the box is emptied", async () => {
    open(on);

    await userEvent.clear(apps());
    await save();

    await saved();
    expect(patches()).toEqual([{ profile: { computer_apps: [] } }]);
    expect(backend.agents[0].computer_apps).toEqual([]);
    expect(apps()).toHaveValue("");
  });

  it("are read from a box the way the server keeps them", () => {
    expect(appLines(" Notes \n\nNotes\n com.apple.Notes")).toEqual(["Notes", "com.apple.Notes"]);
    expect(appLines("\n  \n")).toEqual([]);
  });
});

describe("a save the server refuses", () => {
  const LONG = "A".repeat(201);
  const appsSaid = "agent default: computer_apps must be a list of application names or bundle ids, such as Notes or com.apple.Notes";

  it("shows the refusal of an application beside the box, and keeps what was typed", async () => {
    open({ ...on, computer_apps: [] });

    await userEvent.type(apps(), `Notes{Enter}${LONG}`);
    await save();

    await waitFor(() => expect(controls().getByText(appsSaid)).toHaveClass("field-error"));
    expect(apps()).toHaveValue(`Notes\n${LONG}`);
    expect(apps()).toHaveAttribute("aria-invalid", "true");
    expect(apps()).toHaveAccessibleDescription(`${d.appsHint} ${appsSaid}`);
    expect(screen.getByText(t.dirty(1))).toBeInTheDocument();
    expect(backend.agents[0].computer_apps).toEqual([]);
  });

  it.each(["Safari", "com.google.Chrome"])("shows the refusal of a web browser (%s) beside the box, under the line that says why", async (browser) => {
    open({ ...on, computer_apps: [] });
    const said = `agent default: computer_apps cannot name a web browser (${browser}): the desktop never acts in one; the web is for the browser tools (browser: read or act)`;

    await userEvent.type(apps(), `Notes{Enter}${browser}`);
    await save();

    await waitFor(() => expect(controls().getByText(said)).toHaveClass("field-error"));
    expect(apps()).toHaveValue(`Notes\n${browser}`);
    expect(apps()).toHaveAttribute("aria-invalid", "true");
    expect(apps()).toHaveAccessibleDescription(`${d.appsHint} ${said}`);
    expect(d.appsHint).toContain("Không ghi trình duyệt web (Safari, Chrome, Firefox…)");
    expect(controls().queryByTestId("desktop-mode-error")).not.toBeInTheDocument();
    expect(backend.agents[0].computer_apps).toEqual([]);
  });

  it("keeps the box on screen while the refused list waits to be fixed, even with the mode off", async () => {
    open({ ...on, computer_apps: [] });
    await userEvent.type(apps(), LONG);
    await userEvent.selectOptions(mode(), "off");
    await save();

    await waitFor(() => expect(controls().getByText(appsSaid)).toBeInTheDocument());
    expect(apps()).toHaveValue(LONG);
  });

  it("shows the refusal of the mode beside the select, and keeps the mode chosen", async () => {
    open(off);
    const said = "agent default: computer must be off or on";
    backend.refuseEdit = said;

    await userEvent.selectOptions(mode(), "on");
    await save();

    await waitFor(() => expect(controls().getByTestId("desktop-mode-error")).toHaveTextContent(said));
    expect(mode()).toHaveValue("on");
    expect(mode()).toHaveAttribute("aria-invalid", "true");
    expect(mode()).toHaveAccessibleDescription(`${d.modeHint.on} ${said}`);
  });

  it("does not put a refusal of another key beside either control", async () => {
    open(on);
    backend.refuseEdit = "agent default: max_steps must be a positive number";

    await userEvent.selectOptions(mode(), "off");
    await save();

    await waitFor(() => expect(screen.getByText(t.saveFailed(backend.refuseEdit as string))).toBeInTheDocument());
    expect(controls().queryByTestId("desktop-mode-error")).not.toBeInTheDocument();
    expect(mode()).not.toHaveAttribute("aria-invalid");
  });
});

describe("an agent of a server older than the desktop", () => {
  it("has no desktop control, no word of it under the picker, and sends neither key", async () => {
    open(older);

    expect(screen.queryByTestId("desktop-controls")).not.toBeInTheDocument();
    expect(section().queryByRole("combobox", { name: d.mode })).not.toBeInTheDocument();
    expect(section().queryByText(vi.desktop.outsideList)).not.toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(t.name), "x");
    await save();
    await saved();
    for (const body of patches()) {
      expect(body).not.toHaveProperty("profile.computer");
      expect(body).not.toHaveProperty("profile.computer_apps");
    }
  });
});
