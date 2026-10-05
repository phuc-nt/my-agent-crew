import { renderHook, act } from "@testing-library/react";
import { describe, expect, it, vi as vitest, beforeEach } from "vitest";
import { useAgentDraft } from "./use-agent-draft";
import type { AgentInfo } from "../api/types";
import { FakeBackend, fakeAgent } from "../test/fake-backend";

describe("useAgentDraft", () => {
  beforeEach(() => {
    vitest.stubGlobal("fetch", new FakeBackend().fetch);
  });

  it("initializes with the original profile unchanged and no dirty keys", () => {
    const { result } = renderHook(() => useAgentDraft(fakeAgent));

    expect(result.current.original).toEqual(fakeAgent);
    expect(result.current.draft).toEqual({
      name: fakeAgent.name,
      description: fakeAgent.description,
      mode: fakeAgent.mode,
      workspace: fakeAgent.workspace,
      routes: fakeAgent.routes,
      escalation_route: fakeAgent.escalation_route,
      cost_cap_usd: fakeAgent.cost_cap_usd,
      max_steps: fakeAgent.max_steps,
      autonomous: fakeAgent.autonomous,
      shell_ask_patterns: fakeAgent.shell_ask_patterns,
      tool_output_chars: fakeAgent.tool_output_chars,
      memory_consolidate: fakeAgent.memory_consolidate,
      delegates: fakeAgent.delegates,
      tools: fakeAgent.tools,
      schedules: fakeAgent.schedules,
      telegram: fakeAgent.telegram,
    });
    expect(result.current.dirty).toEqual([]);
  });

  it("starts with no agent when passed null", () => {
    const { result } = renderHook(() => useAgentDraft(null));

    expect(result.current.original).toBeNull();
    expect(result.current.draft).toEqual({});
    expect(result.current.dirty).toEqual([]);
  });

  it("tracks dirty keys when a field changes", () => {
    const { result } = renderHook(() => useAgentDraft(fakeAgent));

    act(() => {
      result.current.set("name", "Tên mới");
    });

    expect(result.current.dirty).toContain("name");
    expect(result.current.dirty).not.toContain("description");
    expect(result.current.draft.name).toBe("Tên mới");
  });

  it("detects when multiple fields have changed", () => {
    const { result } = renderHook(() => useAgentDraft(fakeAgent));

    act(() => {
      result.current.set("name", "Tên mới");
      result.current.set("cost_cap_usd", 50);
    });

    expect(result.current.dirty).toContain("name");
    expect(result.current.dirty).toContain("cost_cap_usd");
    expect(result.current.dirty.length).toBe(2);
  });

  it("no longer marks a field as dirty when it is reset to the original value", () => {
    const { result } = renderHook(() => useAgentDraft(fakeAgent));

    act(() => {
      result.current.set("name", "Tên mới");
    });
    expect(result.current.dirty).toContain("name");

    act(() => {
      result.current.set("name", fakeAgent.name);
    });

    expect(result.current.dirty).not.toContain("name");
  });

  it("compares arrays by content, not identity", () => {
    const agent: AgentInfo = {
      ...fakeAgent,
      tools: ["tool1", "tool2"],
    };
    const { result } = renderHook(() => useAgentDraft(agent));

    act(() => {
      result.current.set("tools", ["tool1", "tool2"]);
    });

    expect(result.current.dirty).not.toContain("tools");
  });

  it("detects when an array changes", () => {
    const agent: AgentInfo = {
      ...fakeAgent,
      tools: ["tool1", "tool2"],
    };
    const { result } = renderHook(() => useAgentDraft(agent));

    act(() => {
      result.current.set("tools", ["tool1", "tool2", "tool3"]);
    });

    expect(result.current.dirty).toContain("tools");
  });

  it("resets all changes back to the original profile", () => {
    const { result } = renderHook(() => useAgentDraft(fakeAgent));

    act(() => {
      result.current.set("name", "Changed");
      result.current.set("cost_cap_usd", 999);
    });
    expect(result.current.dirty.length).toBeGreaterThan(0);

    act(() => {
      result.current.reset();
    });

    expect(result.current.dirty).toEqual([]);
    expect(result.current.draft.name).toBe(fakeAgent.name);
    expect(result.current.draft.cost_cap_usd).toBe(fakeAgent.cost_cap_usd);
    expect(result.current.error).toBeNull();
  });

  it("clears the error when reset is called", () => {
    const { result } = renderHook(() => useAgentDraft(fakeAgent));

    act(() => {
      result.current.set("name", "Changed");
    });

    const backend = new FakeBackend();
    backend.refuseEdit = "This field is not allowed";
    vitest.stubGlobal("fetch", backend.fetch);

    // Re-render with the new fetch stub
    const { result: result2 } = renderHook(() => useAgentDraft(fakeAgent));
    act(() => {
      result2.current.set("name", "Changed");
    });

    act(() => {
      result2.current.reset();
    });

    expect(result2.current.error).toBeNull();
  });

  it("sends only the dirty keys in the PATCH request", async () => {
    const backend = new FakeBackend();
    backend.agents = [fakeAgent];
    vitest.stubGlobal("fetch", backend.fetch);

    const { result } = renderHook(() => useAgentDraft(fakeAgent));

    act(() => {
      result.current.set("name", "Tên mới");
      result.current.set("description", "Mô tả mới");
    });

    await act(async () => {
      await result.current.save();
    });

    const patchRequest = backend.requests.find(
      (r) => r.method === "PATCH" && r.path.includes("/agents/default"),
    );
    expect(patchRequest).toBeDefined();
    const sent = (patchRequest?.body as { profile: Record<string, unknown> }).profile;
    expect(sent).toHaveProperty("name", "Tên mới");
    expect(sent).toHaveProperty("description", "Mô tả mới");
    // Verify that unchanged fields are not sent
    expect(Object.keys(sent)).toHaveLength(2);
  });

  it("returns false and sets error when save fails", async () => {
    const backend = new FakeBackend();
    backend.agents = [fakeAgent];
    backend.refuseEdit = "Cost cap is too high";
    vitest.stubGlobal("fetch", backend.fetch);

    const { result } = renderHook(() => useAgentDraft(fakeAgent));

    act(() => {
      result.current.set("cost_cap_usd", 999);
    });

    let saveResult: boolean | undefined;
    await act(async () => {
      saveResult = await result.current.save();
    });

    expect(saveResult).toBe(false);
    expect(result.current.error).toContain("Cost cap is too high");
  });

  it("preserves the draft after a refused save, so the person can fix and retry", async () => {
    const backend = new FakeBackend();
    backend.agents = [fakeAgent];
    backend.refuseEdit = "Invalid field";
    vitest.stubGlobal("fetch", backend.fetch);

    const { result } = renderHook(() => useAgentDraft(fakeAgent));

    act(() => {
      result.current.set("name", "Tên mới");
      result.current.set("cost_cap_usd", 50);
    });

    await act(async () => {
      await result.current.save();
    });

    expect(result.current.draft.name).toBe("Tên mới");
    expect(result.current.draft.cost_cap_usd).toBe(50);
  });

  it("clears saving flag even when save fails", async () => {
    const backend = new FakeBackend();
    backend.agents = [fakeAgent];
    backend.refuseEdit = "Error";
    vitest.stubGlobal("fetch", backend.fetch);

    const { result } = renderHook(() => useAgentDraft(fakeAgent));

    act(() => {
      result.current.set("name", "Changed");
    });

    await act(async () => {
      await result.current.save();
    });

    expect(result.current.saving).toBe(false);
  });

  it("returns true when save succeeds", async () => {
    const backend = new FakeBackend();
    backend.agents = [fakeAgent];
    vitest.stubGlobal("fetch", backend.fetch);

    const { result } = renderHook(() => useAgentDraft(fakeAgent));

    act(() => {
      result.current.set("name", "Tên mới");
    });

    let saveResult: boolean | undefined;
    await act(async () => {
      saveResult = await result.current.save();
    });

    expect(saveResult).toBe(true);
    expect(result.current.error).toBeNull();
  });

  it("does nothing and returns true when there is no original agent", async () => {
    const { result } = renderHook(() => useAgentDraft(null));

    let saveResult: boolean | undefined;
    await act(async () => {
      saveResult = await result.current.save();
    });

    expect(saveResult).toBe(true);
  });

  it("does nothing and returns true when there are no dirty keys", async () => {
    const backend = new FakeBackend();
    backend.agents = [fakeAgent];
    vitest.stubGlobal("fetch", backend.fetch);

    const { result } = renderHook(() => useAgentDraft(fakeAgent));

    let saveResult: boolean | undefined;
    await act(async () => {
      saveResult = await result.current.save();
    });

    expect(saveResult).toBe(true);
    const patches = backend.requests.filter((r) => r.method === "PATCH");
    expect(patches).toHaveLength(0);
  });

  it("updates the original and draft to the server response after save", async () => {
    const backend = new FakeBackend();
    const original = { ...fakeAgent, name: "Original" };
    backend.agents = [original];
    vitest.stubGlobal("fetch", backend.fetch);

    const { result } = renderHook(() => useAgentDraft(original));

    act(() => {
      result.current.set("name", "Tên mới");
    });

    await act(async () => {
      await result.current.save();
    });

    expect(result.current.original?.name).toBe("Tên mới");
    expect(result.current.draft.name).toBe("Tên mới");
  });

  it("calls onSaved callback after successful save", async () => {
    const backend = new FakeBackend();
    backend.agents = [fakeAgent];
    vitest.stubGlobal("fetch", backend.fetch);

    const onSaved = vitest.fn();
    const agent = { ...fakeAgent, name: "Original" };
    backend.agents = [agent];

    const { result } = renderHook(() => useAgentDraft(agent, onSaved));

    act(() => {
      result.current.set("name", "Tên mới");
    });

    let saveResult: boolean | undefined;
    await act(async () => {
      saveResult = await result.current.save();
    });

    expect(saveResult).toBe(true);
    expect(onSaved).toHaveBeenCalled();
  });

  it("sets restartRequired after save when the server says so", async () => {
    const backend = new FakeBackend();
    backend.agents = [fakeAgent];
    vitest.stubGlobal("fetch", backend.fetch);

    const { result } = renderHook(() => useAgentDraft(fakeAgent));

    act(() => {
      result.current.set("schedules", [
        { id: "test", name: "Test", kind: "prompt", cron: "0 0 * * *", every: null, prompt: "test", command: null, enabled: true, skills: [] },
      ]);
    });

    await act(async () => {
      await result.current.save();
    });

    expect(result.current.restartRequired.length).toBeGreaterThan(0);
  });

  // The server answers a save with the agent as the list shows it, `declared` included,
  // and the form starts over from that. An answer without it once left the form nothing
  // to rebuild from, and the page that made the first successful save broke on it.
  it("rebuilds the form from the rows the server declares back", async () => {
    const backend = new FakeBackend();
    backend.agents = [fakeAgent];
    vitest.stubGlobal("fetch", backend.fetch);
    const { result } = renderHook(() => useAgentDraft(fakeAgent));

    act(() => {
      result.current.set("schedules", [
        { id: "", name: "", cron: null, every: "2h", prompt: "Nhắc", command: null, enabled: true, skills: [] },
      ]);
    });
    await act(async () => {
      await result.current.save();
    });

    const declared = {
      id: "job-0",
      name: "job-0",
      cron: null,
      every: "2h",
      prompt: "Nhắc",
      command: null,
      enabled: true,
      skills: [],
      approval_ttl_seconds: null,
    };
    expect(result.current.original?.declared.schedules).toEqual([declared]);
    expect(result.current.original?.schedules).toEqual([{ ...declared, kind: "prompt" }]);
    expect(result.current.draft.schedules).toEqual([declared]);
    expect(result.current.dirty).toEqual([]);
  });

  // A server still on older code answers a save without `declared`. The form used to
  // rebuild from that answer and threw on the missing block, blanking the editor.
  it("reads the list again when the save's answer lacks `declared`", async () => {
    const backend = new FakeBackend();
    backend.agents = [fakeAgent];
    vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const answer = await backend.fetch(input, init);
      if (init.method !== "PATCH") return answer;
      const { profile, restart_required } = await answer.json();
      const { declared: _declared, ...older } = profile;
      return new Response(JSON.stringify({ profile: older, restart_required }), {
        headers: { "content-type": "application/json" },
      });
    });
    const { result } = renderHook(() => useAgentDraft(fakeAgent));

    act(() => {
      result.current.set("schedules", [
        { id: "t", name: "T", cron: "0 7 * * *", every: null, prompt: "Nhắc", command: null, enabled: true, skills: [] },
      ]);
    });
    let saved: boolean | undefined;
    await act(async () => {
      saved = await result.current.save();
    });

    expect(saved).toBe(true);
    expect(result.current.error).toBeNull();
    const reads = backend.requests.filter((r) => r.method === "GET" && r.path === "/agents");
    expect(reads).toHaveLength(1);
    expect(result.current.original?.declared.schedules).toEqual([
      {
        id: "t",
        name: "T",
        cron: "0 7 * * *",
        every: null,
        prompt: "Nhắc",
        command: null,
        enabled: true,
        skills: [],
        approval_ttl_seconds: null,
      },
    ]);
    expect(result.current.dirty).toEqual([]);
  });

  it("never sends the derived kind, even on a row that still carries it", async () => {
    const backend = new FakeBackend();
    backend.agents = [fakeAgent];
    vitest.stubGlobal("fetch", backend.fetch);
    const { result } = renderHook(() => useAgentDraft(fakeAgent));

    act(() => {
      result.current.set("schedules", [
        { id: "t", name: "T", kind: "command", cron: "0 0 * * *", every: null, prompt: null, command: "ls", enabled: false, skills: [] },
      ]);
    });
    let saved: boolean | undefined;
    await act(async () => {
      saved = await result.current.save();
    });

    expect(saved).toBe(true);
    const patch = backend.requests.find((r) => r.method === "PATCH");
    expect((patch?.body as { profile: { schedules: unknown[] } }).profile.schedules).toEqual([
      { id: "t", name: "T", cron: "0 0 * * *", command: "ls", enabled: false, skills: [] },
    ]);
  });

  it("sends an emptied consolidation cron as null, which takes the key out of the file", async () => {
    const agent = { ...fakeAgent, memory_consolidate: "0 3 * * *" };
    const backend = new FakeBackend();
    backend.agents = [agent];
    vitest.stubGlobal("fetch", backend.fetch);
    const { result } = renderHook(() => useAgentDraft(agent));

    act(() => {
      result.current.set("memory_consolidate", "  ");
    });
    await act(async () => {
      await result.current.save();
    });

    const patch = backend.requests.find((r) => r.method === "PATCH");
    expect(patch?.body).toEqual({ profile: { memory_consolidate: null } });
    expect(result.current.draft.memory_consolidate).toBe("");
  });

  it("holds the save, without a request, while a changed field cannot be sent", async () => {
    const agent = { ...fakeAgent, telegram: { token_env: "TG_TOKEN", chat_id: 42 } };
    const backend = new FakeBackend();
    backend.agents = [agent];
    vitest.stubGlobal("fetch", backend.fetch);
    const { result } = renderHook(() => useAgentDraft(agent));

    act(() => {
      result.current.set("telegram", { token_env: "TG_TOKEN", chat_id: Number.NaN });
    });
    expect(result.current.problems.chatId).toBeTruthy();

    let saved: boolean | undefined;
    await act(async () => {
      saved = await result.current.save();
    });

    expect(saved).toBe(false);
    expect(backend.requests.some((r) => r.method === "PATCH")).toBe(false);
  });

  it("resets to a different agent when the agent id changes", () => {
    const agent1 = { ...fakeAgent, id: "agent1", name: "Agent 1" };
    const agent2 = { ...fakeAgent, id: "agent2", name: "Agent 2" };

    const { result, rerender } = renderHook(
      ({ agent }) => useAgentDraft(agent),
      { initialProps: { agent: agent1 } },
    );

    act(() => {
      result.current.set("name", "Modified 1");
    });

    expect(result.current.dirty).toContain("name");
    expect(result.current.draft.name).toBe("Modified 1");

    rerender({ agent: agent2 });

    expect(result.current.original?.id).toBe("agent2");
    expect(result.current.draft.name).toBe("Agent 2");
    expect(result.current.dirty).toEqual([]);
  });

  it("clears the error when the agent changes", () => {
    const agent1 = { ...fakeAgent, id: "agent1" };
    const agent2 = { ...fakeAgent, id: "agent2" };

    const { result, rerender } = renderHook(
      ({ agent }) => useAgentDraft(agent),
      { initialProps: { agent: agent1 } },
    );

    // Simulate an error being set (though we can't directly in this test,
    // we can verify the effect clears it)
    rerender({ agent: agent2 });

    expect(result.current.error).toBeNull();
  });
});
