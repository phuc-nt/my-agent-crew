// A crew older than the two script switches reports neither for an agent, and runs it as the
// form shows: scripts call what reads, and may ask the model. Choosing something else and
// choosing back is no change: the form has nothing to save.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentInfo } from "../../api/types";
import { vi } from "../../i18n/vi";
import { FakeBackend, fakeAgent } from "../../test/fake-backend";
import { AgentEditor } from "./agent-editor";

const t = vi.editor;

beforeEach(() => {
  vitest.stubGlobal("fetch", new FakeBackend().fetch);
});

/** Opens the editor on the agent as that crew reports it: with neither key. */
function open() {
  const { script_calls: _calls, script_llm: _llm, ...agent }: AgentInfo = fakeAgent;
  expect(agent).not.toHaveProperty("script_calls");
  expect(agent).not.toHaveProperty("script_llm");
  render(<AgentEditor agent={agent} agents={[agent]} tools={[]} mcpServers={[]} providers={[]} onBack={() => {}} onChanged={() => {}} />);
}

const section = () => within(screen.getByTestId("section-tools"));
const calls = () => section().getByRole("combobox", { name: t.scriptCalls });
const llm = () => section().getByRole("checkbox", { name: t.scriptLlm });

function nothingToSave() {
  expect(screen.getByText(t.clean)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: t.save })).toBeDisabled();
}

describe("a script setting chosen and chosen back, on an agent whose crew reports none", () => {
  it.each(["gated", "none"])("leaves nothing to save for what scripts may call, by way of %s", async (other) => {
    open();

    await userEvent.selectOptions(calls(), other);
    expect(screen.getByText(t.dirty(1))).toBeInTheDocument();
    await userEvent.selectOptions(calls(), "read_only");

    expect(calls()).toHaveValue("read_only");
    nothingToSave();
  });

  it("leaves nothing to save for whether scripts may ask the model", async () => {
    open();

    await userEvent.click(llm());
    expect(llm()).not.toBeChecked();
    expect(screen.getByText(t.dirty(1))).toBeInTheDocument();
    await userEvent.click(llm());

    expect(llm()).toBeChecked();
    nothingToSave();
  });
});
