// Autonomy is ticked at the top of the form; what scripts may call is chosen far below, with
// the tools. On an agent whose scripts may change things the two mean together that nobody
// is asked. The line that says so stands under the tick as well as under the select, so that
// whoever sets either one reads it where they set it.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentInfo, ScriptCalls } from "../../api/types";
import { vi } from "../../i18n/vi";
import { FakeBackend, fakeAgent } from "../../test/fake-backend";
import { AgentEditor } from "./agent-editor";

const t = vi.editor;
const LINE = t.scriptCallsGatedAutonomous;

beforeEach(() => {
  vitest.stubGlobal("fetch", new FakeBackend().fetch);
});

function open(agent: AgentInfo) {
  render(<AgentEditor agent={agent} agents={[agent]} tools={[]} mcpServers={[]} providers={[]} onBack={() => {}} onChanged={() => {}} />);
}
const as = (script_calls: ScriptCalls, autonomous: boolean, more: Partial<AgentInfo> = {}): AgentInfo => ({ ...fakeAgent, script_calls, autonomous, ...more });

const identity = () => within(screen.getByTestId("section-identity"));
const tick = () => identity().getByRole("checkbox", { name: t.autonomous });
const calls = () => within(screen.getByTestId("section-tools")).getByRole("combobox", { name: t.scriptCalls });
/** The line under the tick, if it is there. */
const line = () => identity().queryByText(LINE);

function saysSo() {
  expect(tick()).toHaveAccessibleDescription(LINE);
  expect(line()).toHaveClass("warn-text");
  // Under the box that was ticked, in the same field.
  expect(line()?.closest(".check-field")).toBe(tick().closest(".check-field"));
  expect(tick().compareDocumentPosition(line() as Node) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
}
function saysNothing() {
  expect(line()).not.toBeInTheDocument();
  expect(tick()).not.toHaveAccessibleDescription();
}

describe("the line under the autonomy tick that says nobody will be asked", () => {
  it("appears when autonomy is ticked on an agent whose scripts may already change things", async () => {
    open(as("gated", false));
    saysNothing();

    await userEvent.click(tick());
    saysSo();
    // The same words the select carries, a few sections down.
    expect(calls()).toHaveAccessibleDescription(LINE);

    await userEvent.click(tick());
    saysNothing();
  });

  it("appears when scripts are let change things on an agent that already runs by itself", async () => {
    open(as("read_only", true));
    saysNothing();

    await userEvent.selectOptions(calls(), "gated");
    saysSo();

    await userEvent.selectOptions(calls(), "none");
    saysNothing();
  });

  it("is there from the start on an agent saved with both", () => {
    open(as("gated", true));

    saysSo();
    expect(screen.getByText(t.clean)).toBeInTheDocument();
  });

  // Whoever cannot change the agent still reads what it does.
  it("is there on an agent this form does not edit", () => {
    open(as("gated", true, { editable: false }));

    expect(tick()).toBeDisabled();
    saysSo();
  });

  it.each<[string, ScriptCalls, boolean]>([
    ["runs by itself and its scripts only read", "read_only", true],
    ["runs by itself and has no script tool", "none", true],
    ["asks before it changes things, whatever its scripts may call", "gated", false],
    ["asks, and its scripts only read", "read_only", false],
  ])("is not there on an agent that %s", (_name, scriptCalls, autonomous) => {
    open(as(scriptCalls, autonomous));

    saysNothing();
  });

  it("is not there on an autonomous agent whose crew reports no script setting", () => {
    const { script_calls: _calls, ...older } = as("gated", true);
    open(older);

    saysNothing();
  });
});
