import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import type { AgentInfo } from "../../api/types";
import { parseRoute } from "../../hooks/use-route";
import { vi } from "../../i18n/vi";
import { FakeBackend, fakeAgent } from "../../test/fake-backend";
import { AgentEditor } from "./agent-editor";

const t = vi.editor;

function open(agent: AgentInfo) {
  const backend = new FakeBackend();
  backend.agents = [agent];
  vitest.stubGlobal("fetch", backend.fetch);
  render(<AgentEditor agent={agent} agents={[agent]} tools={[]} mcpServers={[]} providers={[]} onBack={() => {}} onChanged={() => {}} />);
}

const link = () => screen.queryByRole("link", { name: t.scriptStoreLink });
const llm = () => screen.getByRole("checkbox", { name: t.scriptLlm });

describe("the way from an agent's script settings to what its scripts keep", () => {
  it("is a link to the store screen with this agent chosen, after the two settings", () => {
    open({ ...fakeAgent, id: "coach" });

    expect(link()).toHaveAttribute("href", "#/manage/memory/scripts/coach");
    // The address the memory screen reads as the store of one agent.
    expect(parseRoute("#/manage/memory/scripts/coach")).toMatchObject({ kind: "manage", section: "memory", param: "scripts", focus: "coach" });
    expect(within(screen.getByTestId("section-tools")).getByRole("link", { name: t.scriptStoreLink })).toBe(link());
    expect(llm().compareDocumentPosition(link() as Node) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  // Reading what an agent keeps changes nothing of the agent.
  it("is there for an agent that is not edited here", () => {
    open({ ...fakeAgent, id: "coach", editable: false });

    expect(llm()).toBeDisabled();
    expect(link()).toHaveAttribute("href", "#/manage/memory/scripts/coach");
  });
});
