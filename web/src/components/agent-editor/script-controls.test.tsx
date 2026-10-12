import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi as vitest } from "vitest";
import type { AgentInfo } from "../../api/types";
import { vi } from "../../i18n/vi";
import { FakeBackend, fakeAgent } from "../../test/fake-backend";
import { AgentEditor } from "./agent-editor";

const t = vi.editor;
let backend: FakeBackend;
let shown: { unmount: () => void };

function open(agent: AgentInfo) {
  backend = new FakeBackend();
  backend.agents = [agent];
  vitest.stubGlobal("fetch", backend.fetch);
  mount(agent);
}

function mount(agent: AgentInfo) {
  shown = render(<AgentEditor agent={agent} agents={[agent]} tools={[]} mcpServers={[]} providers={[]} onBack={() => {}} onChanged={() => {}} />);
}

/** The agent as a crew older than the two keys reports it. */
function older(): AgentInfo {
  const { script_calls: _calls, script_llm: _llm, ...rest } = fakeAgent;
  return rest;
}

const section = () => within(screen.getByTestId("section-tools"));
const calls = () => section().getByRole("combobox", { name: t.scriptCalls }) as HTMLSelectElement;
const llm = () => section().getByRole("checkbox", { name: t.scriptLlm });
const save = () => userEvent.click(screen.getByRole("button", { name: t.save }));
const saved = () => waitFor(() => expect(screen.getByText(t.clean)).toBeInTheDocument());
const patches = () => backend.requests.filter((r) => r.method === "PATCH").map((r) => r.body);

describe("what an agent's scripts may call", () => {
  it("offers the three values the file takes, under words of their own", () => {
    open(fakeAgent);

    expect(within(calls()).getAllByRole("option").map((o) => [(o as HTMLOptionElement).value, o.textContent])).toEqual([
      ["none", t.scriptCallsOption.none],
      ["read_only", t.scriptCallsOption.read_only],
      ["gated", t.scriptCallsOption.gated],
    ]);
  });

  it("opens on what the file says", () => {
    open({ ...fakeAgent, script_calls: "gated", script_llm: false });

    expect(calls()).toHaveValue("gated");
    expect(llm()).not.toBeChecked();
    expect(screen.getByText(t.clean)).toBeInTheDocument();
  });

  it("opens on what the crew runs an agent as, for a server that reports neither key", async () => {
    const agent = older();
    expect(agent).not.toHaveProperty("script_calls");
    expect(agent).not.toHaveProperty("script_llm");
    open(agent);

    expect(calls()).toHaveValue("read_only");
    expect(llm()).toBeChecked();
    // Nothing was chosen, so there is nothing to save; a choice is sent alone.
    expect(screen.getByText(t.clean)).toBeInTheDocument();
    await userEvent.selectOptions(calls(), "gated");
    await save();
    await saved();
    expect(patches()).toEqual([{ profile: { script_calls: "gated" } }]);
  });

  it.each(["none", "gated"] as const)("saves %s as the one key that changed, with no restart asked", async (value) => {
    open(fakeAgent);

    await userEvent.selectOptions(calls(), value);
    expect(screen.getByText(t.dirty(1))).toBeInTheDocument();
    await save();

    await saved();
    expect(patches()).toEqual([{ profile: { script_calls: value } }]);
    // The answer to the save is what the form is rebuilt from.
    expect(calls()).toHaveValue(value);
    expect(screen.queryByTestId("restart-banner")).not.toBeInTheDocument();
  });

  it("is still what the editor shows when the agent is opened again", async () => {
    open(fakeAgent);
    await userEvent.selectOptions(calls(), "none");
    await userEvent.click(llm());
    await save();
    await saved();
    expect(patches()).toEqual([{ profile: { script_calls: "none", script_llm: false } }]);

    shown.unmount();
    mount(backend.agents[0]);

    expect(calls()).toHaveValue("none");
    expect(llm()).not.toBeChecked();
    expect(screen.getByText(t.clean)).toBeInTheDocument();
  });

  it("has nothing to save once the choice is taken back", async () => {
    open(fakeAgent);

    await userEvent.selectOptions(calls(), "gated");
    await userEvent.selectOptions(calls(), "read_only");

    expect(screen.getByText(t.clean)).toBeInTheDocument();
  });

  it("cannot be changed on an agent that is not edited here", () => {
    open({ ...fakeAgent, editable: false, script_calls: "gated", script_llm: false });

    expect(calls()).toBeDisabled();
    expect(calls()).toHaveValue("gated");
    expect(llm()).toBeDisabled();
    expect(llm()).not.toBeChecked();
  });
});

describe("the line under the choice", () => {
  it("is the description of the select, and follows the option chosen", async () => {
    open(fakeAgent);
    expect(calls()).toHaveAccessibleDescription(t.scriptCallsHint.read_only);

    await userEvent.selectOptions(calls(), "none");
    expect(calls()).toHaveAccessibleDescription(t.scriptCallsHint.none);
    // A schedule's own script is not switched off with the tool.
    expect(t.scriptCallsHint.none).toContain("Script của một lịch chạy vẫn chạy");

    await userEvent.selectOptions(calls(), "gated");
    expect(calls()).toHaveAccessibleDescription(t.scriptCallsHint.gated);
  });

  it("says of gated what autonomy does to it, before the agent has any", async () => {
    open({ ...fakeAgent, autonomous: false });

    await userEvent.selectOptions(calls(), "gated");

    expect(section().getByText(t.scriptCallsHint.gated)).toBeInTheDocument();
    expect(t.scriptCallsHint.gated).toContain("cổng duyệt");
    expect(t.scriptCallsHint.gated).toContain("Nếu agent tự chủ, các lời gọi ấy chạy luôn, không ai được hỏi.");
  });

  it("says it of this agent, as a warning, once the form has both switched on", async () => {
    open({ ...fakeAgent, autonomous: false, script_calls: "gated" });
    const autonomy = within(screen.getByTestId("section-identity")).getByRole("checkbox", { name: t.autonomous });

    await userEvent.click(autonomy);

    expect(calls()).toHaveAccessibleDescription(t.scriptCallsGatedAutonomous);
    expect(section().getByText(t.scriptCallsGatedAutonomous)).toHaveClass("warn-text");
    expect(t.scriptCallsGatedAutonomous).toContain("không ai được hỏi");
    expect(section().queryByText(t.scriptCallsHint.gated)).not.toBeInTheDocument();

    // Autonomy alone changes nothing a script may call.
    await userEvent.selectOptions(calls(), "read_only");
    expect(calls()).toHaveAccessibleDescription(t.scriptCallsHint.read_only);
    expect(section().queryByText(t.scriptCallsGatedAutonomous)).not.toBeInTheDocument();
  });
});

describe("whether an agent's scripts may ask a model", () => {
  it("is switched off with one tick and a save, and nothing else is sent", async () => {
    open(fakeAgent);
    expect(llm()).toBeChecked();

    await userEvent.click(llm());
    expect(screen.getByText(t.dirty(1))).toBeInTheDocument();
    await save();

    await saved();
    expect(patches()).toEqual([{ profile: { script_llm: false } }]);
    expect(llm()).not.toBeChecked();
    expect(screen.queryByTestId("restart-banner")).not.toBeInTheDocument();
  });

  it("says what it costs and that a schedule's script is covered, as its description", () => {
    open(fakeAgent);

    expect(llm()).toHaveAccessibleDescription(t.scriptLlmHint);
    expect(t.scriptLlmHint).toContain("tốn tiền");
    expect(t.scriptLlmHint).toContain("script của lịch chạy");
  });

  it("stays on offer for an agent handed no script tool: its schedules' scripts still run", async () => {
    open({ ...fakeAgent, script_calls: "none", script_llm: false });

    expect(llm()).toBeEnabled();
    await userEvent.click(llm());
    await save();

    await saved();
    expect(patches()).toEqual([{ profile: { script_llm: true } }]);
    expect(llm()).toBeChecked();
  });
});
