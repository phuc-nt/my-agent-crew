import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { api } from "../api/client";
import type { McpServerInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { FakeBackend, coachAgent, fakeAgent } from "../test/fake-backend";
import { SIGN_IN_LOCAL_ONLY, authorizeUrl, mcpServer, mcpTool } from "../test/fake-mcp";
import { KEY_POLLS, POLL_MS, TRY_POLLS, handedOut, standing, useMcpServers } from "./use-mcp-servers";

let backend: FakeBackend;

const reads = () => backend.requests.filter((r) => r.method === "GET" && r.path === "/mcp").length;
const posted = () => backend.requests.filter((r) => r.method !== "GET").map((r) => `${r.method} ${r.path}`);
const seed = (...servers: McpServerInfo[]) => {
  backend.mcp.servers = servers;
};

/** Let `polls` poll intervals go by, one at a time so each read lands before the next. */
async function pass(polls: number) {
  for (let i = 0; i < polls; i += 1) {
    await act(async () => {
      await vitest.advanceTimersByTimeAsync(POLL_MS);
    });
  }
}

async function opened(leave?: (url: string) => void) {
  const hook = renderHook(() => useMcpServers(leave));
  await waitFor(() => expect(reads()).toBe(1));
  await waitFor(() => expect(hook.result.current.servers).toHaveLength(backend.mcp.servers.length));
  return hook;
}

const statuses = (hook: Awaited<ReturnType<typeof opened>>) => hook.result.current.servers.map((s) => s.status);

beforeEach(() => {
  // `shouldAdvanceTime` keeps `waitFor` and the request's own microtasks moving while the
  // test still jumps the poll interval forward on its own terms.
  vitest.useFakeTimers({ shouldAdvanceTime: true });
  backend = new FakeBackend();
  vitest.stubGlobal("fetch", backend.fetch);
});
afterEach(() => {
  vitest.useRealTimers();
  vitest.unstubAllGlobals();
  vitest.restoreAllMocks();
});

describe("the list of MCP servers", () => {
  it("is read when the page opens, and not again while every server has an answer", async () => {
    seed(mcpServer(), mcpServer({ name: "wiki", status: "signed_out" }), mcpServer({ name: "old", status: "failed" }));
    const hook = await opened();

    expect(statuses(hook)).toEqual(["connected", "signed_out", "failed"]);
    expect(hook.result.current.error).toBeNull();
    await pass(4);
    expect(reads()).toBe(1);
  });

  it("is read again every couple of seconds while a server is being tried, until it has an answer", async () => {
    seed(mcpServer({ status: "idle" }));
    const hook = await opened();
    expect(statuses(hook)).toEqual(["idle"]);

    // Well short of the interval nothing is asked. (The clock also runs on its own here,
    // so the test stays clear of the edge.)
    await act(async () => {
      await vitest.advanceTimersByTimeAsync(POLL_MS / 2);
    });
    expect(reads()).toBe(1);
    await act(async () => {
      await vitest.advanceTimersByTimeAsync(POLL_MS / 2);
    });
    await waitFor(() => expect(reads()).toBe(2));

    seed(mcpServer({ status: "connected", tools: [mcpTool("notion", "search")] }));
    await pass(1);
    await waitFor(() => expect(statuses(hook)).toEqual(["connected"]));
    expect(hook.result.current.servers[0].tools).toHaveLength(1);
    expect(reads()).toBe(3);

    await pass(4);
    expect(reads()).toBe(3);
  });

  it("stops asking about a server that never answers, and starts again on a refresh", async () => {
    seed(mcpServer({ status: "idle" }));
    const hook = await opened();

    await pass(TRY_POLLS + 6);
    expect(reads()).toBe(1 + TRY_POLLS);

    await act(() => hook.result.current.refresh());
    expect(reads()).toBe(2 + TRY_POLLS);
    await pass(2);
    expect(reads()).toBe(4 + TRY_POLLS);
  });

  it("leaves a server that is down alone, until a key changes and then for a short while", async () => {
    seed(mcpServer({ status: "failed", error: "HTTP 401" }));
    const hook = await opened();
    await pass(3);
    expect(reads()).toBe(1);

    await act(() => hook.result.current.keysChanged());
    expect(reads()).toBe(2);
    await pass(KEY_POLLS + 4);
    expect(reads()).toBe(2 + KEY_POLLS);
    expect(statuses(hook)).toEqual(["failed"]);
  });

  // A key in a header is no sign-in: only the owner can give a server one, so nothing the
  // crew does on its own would change that row.
  it("does not watch a server that waits for a sign-in, even after a key changed", async () => {
    seed(mcpServer({ status: "signed_out" }), mcpServer({ name: "wiki" }));
    const hook = await opened();

    await act(() => hook.result.current.keysChanged());
    expect(reads()).toBe(2);
    await pass(KEY_POLLS);

    expect(reads()).toBe(2);
    expect(statuses(hook)).toEqual(["signed_out", "connected"]);
  });

  it("shows a server that came up after a key changed, and stops there", async () => {
    seed(mcpServer({ status: "failed", error: "HTTP 401" }));
    const hook = await opened();

    await act(() => hook.result.current.keysChanged());
    backend.mcp.becomes("notion", { status: "connected", error: "" });
    backend.mcp.wake();
    await pass(1);

    await waitFor(() => expect(statuses(hook)).toEqual(["connected"]));
    expect(hook.result.current.servers[0].error).toBe("");
    const settled = reads();
    await pass(KEY_POLLS);
    expect(reads()).toBe(settled);
  });

  it("says why it could not be read, and drops that once it can", async () => {
    seed(mcpServer());
    vitest.stubGlobal("fetch", async () => {
      throw new TypeError("Failed to fetch");
    });
    const hook = renderHook(() => useMcpServers());
    await waitFor(() => expect(hook.result.current.error).toBe(vi.requestErrors.network));
    expect(hook.result.current.servers).toEqual([]);

    vitest.stubGlobal("fetch", backend.fetch);
    await act(() => hook.result.current.refresh());

    expect(hook.result.current.error).toBeNull();
    expect(statuses(hook)).toEqual(["connected"]);
  });

  it("keeps the answer of the request made last when two cross", async () => {
    let land: (answer: { servers: McpServerInfo[] }) => void = () => {};
    const slow = new Promise<{ servers: McpServerInfo[] }>((resolve) => {
      land = resolve;
    });
    vitest.spyOn(api, "mcpServers").mockReturnValueOnce(slow);
    seed(mcpServer({ status: "failed" }));
    backend.mcp.becomes("notion", { status: "connected" });
    const hook = renderHook(() => useMcpServers());

    await act(() => hook.result.current.reconnect("notion"));
    expect(statuses(hook)).toEqual(["connected"]);

    // The read made when the page opened only lands now, with what was true before.
    await act(async () => {
      land({ servers: [mcpServer({ status: "failed" })] });
      await slow;
    });
    expect(statuses(hook)).toEqual(["connected"]);
  });
});

describe("trying a server again", () => {
  it("takes the list the request answers, without a second read", async () => {
    seed(mcpServer({ status: "failed", error: "connection refused" }));
    backend.mcp.becomes("notion", { status: "connected", error: "", tools: [mcpTool("notion", "search")] });
    const hook = await opened();

    await act(() => hook.result.current.reconnect("notion"));

    expect(posted()).toEqual(["POST /mcp/notion/reconnect"]);
    expect(statuses(hook)).toEqual(["connected"]);
    expect(hook.result.current.servers[0].tools.map((tool) => tool.remote)).toEqual(["search"]);
    expect(reads()).toBe(1);
  });

  it("watches a server the request left being tried, even after the page gave up on it", async () => {
    seed(mcpServer({ status: "idle" }));
    const hook = await opened();
    await pass(TRY_POLLS + 2);
    const before = reads();

    await act(() => hook.result.current.reconnect("notion"));
    await pass(2);

    expect(reads()).toBe(before + 2);
  });

  it("rejects with the server's own words for a name it does not know, and keeps the list", async () => {
    seed(mcpServer());
    const hook = await opened();

    await expect(hook.result.current.reconnect("ghost")).rejects.toMatchObject({
      status: 404,
      message: "Không có máy chủ MCP tên ghost.",
    });
    expect(statuses(hook)).toEqual(["connected"]);
  });
});

describe("signing in and out", () => {
  it("sends the person to the address the server answers", async () => {
    seed(mcpServer({ status: "signed_out" }));
    const leave = vitest.fn();
    const hook = await opened(leave);

    await act(() => hook.result.current.signIn("notion"));

    expect(posted()).toEqual(["POST /mcp/notion/login"]);
    expect(leave).toHaveBeenCalledTimes(1);
    expect(leave).toHaveBeenCalledWith(authorizeUrl("notion"));
  });

  it("goes nowhere when the server refuses, and rejects with its reason", async () => {
    seed(mcpServer({ status: "signed_out" }));
    backend.mcp.refuseSignIn = SIGN_IN_LOCAL_ONLY;
    const leave = vitest.fn();
    const hook = await opened(leave);

    await expect(hook.result.current.signIn("notion")).rejects.toMatchObject({ status: 409, message: SIGN_IN_LOCAL_ONLY });
    expect(leave).not.toHaveBeenCalled();
  });

  it("watches another server still being tried after a sign-out, even after the page gave up on it", async () => {
    seed(mcpServer({ signed_in: true }), mcpServer({ name: "wiki", status: "idle" }));
    const hook = await opened();
    await pass(TRY_POLLS + 2);
    const before = reads();

    await act(() => hook.result.current.signOut("notion"));
    await pass(2);

    expect(reads()).toBe(before + 2);
    expect(statuses(hook)).toEqual(["signed_out", "idle"]);
  });

  it("shows a server signed out of as waiting for a sign-in, with no tools", async () => {
    seed(mcpServer({ signed_in: true, tools: [mcpTool("notion", "search")] }));
    const hook = await opened();

    await act(() => hook.result.current.signOut("notion"));

    expect(posted()).toEqual(["DELETE /mcp/notion/login"]);
    const [server] = hook.result.current.servers;
    expect(server).toMatchObject({ status: "signed_out", signed_in: false, tools: [] });
    expect(reads()).toBe(1);
  });
});

// Who uses a server is read off the agents' own lists, and no try of a server changes it:
// it changes when an agent is written, made or removed, which the page is the one to say.
describe("when the crew changes", () => {
  it("reads the list again, which says who uses each server now", async () => {
    backend.agents = [{ ...fakeAgent, mcp: ["notion"] }, coachAgent];
    seed(mcpServer());
    const hook = await opened();
    expect(hook.result.current.servers[0].agents).toEqual(["default"]);

    backend.agents = [fakeAgent, { ...coachAgent, mcp: ["notion"] }];
    await act(() => hook.result.current.crewChanged());

    expect(reads()).toBe(2);
    expect(hook.result.current.servers[0].agents).toEqual(["coach"]);
    // No server was tried for it, so there is nothing to watch.
    await pass(3);
    expect(reads()).toBe(2);
  });

  // After a key changed the crew tries the servers that are down on its own time, and an
  // agent saved meanwhile is no reason to stop looking.
  it("goes on watching the servers that are down after a key changed", async () => {
    seed(mcpServer({ status: "failed", error: "HTTP 401" }));
    const hook = await opened();
    await act(() => hook.result.current.keysChanged());

    await act(() => hook.result.current.crewChanged());
    expect(reads()).toBe(3);
    await pass(KEY_POLLS + 4);

    expect(reads()).toBe(3 + KEY_POLLS);
  });

  it("says why the list could not be read, and keeps the one it has", async () => {
    backend.agents = [{ ...fakeAgent, mcp: ["notion"] }];
    seed(mcpServer());
    const hook = await opened();
    vitest.stubGlobal("fetch", async () => {
      throw new TypeError("Failed to fetch");
    });

    await act(() => hook.result.current.crewChanged());

    expect(hook.result.current.error).toBe(vi.requestErrors.network);
    expect(hook.result.current.servers[0].agents).toEqual(["default"]);
  });
});

// The manage screen hands `keysChanged` to the credentials hook, which reads the keys again
// whenever the callback it was given changes.
describe("what the servers hand out, as one value", () => {
  const search = mcpTool("notion", "search");
  const create = mcpTool("notion", "create-pages");
  const base = [mcpServer({ tools: [search, create] }), mcpServer({ name: "wiki", tools: [] })];

  it("stays the same for the same tools, whatever else a server reads as", () => {
    const later = [
      mcpServer({ tools: [{ ...search }, { ...create }], status: "failed", error: "hết giờ", agents: ["coach"] }),
      mcpServer({ name: "wiki", tools: [], status: "idle", signed_in: true }),
    ];

    expect(handedOut(later)).toBe(handedOut(base));
  });

  it("is the same with and without the servers that hold no tool", () => {
    expect(handedOut([base[0]])).toBe(handedOut(base));
    expect(handedOut([mcpServer({ status: "idle" }), base[1]])).toBe(handedOut([]));
  });

  it.each<[string, McpServerInfo[]]>([
    ["a tool gone", [mcpServer({ tools: [search] }), base[1]]],
    ["every tool gone", [mcpServer({ tools: [] }), base[1]]],
    ["a tool let in another way", [mcpServer({ tools: [{ ...search, exposure: "direct" }, create] }), base[1]]],
    ["a tool that no longer asks", [mcpServer({ tools: [search, { ...create, requires_approval: false }] }), base[1]]],
    ["a tool described anew", [mcpServer({ tools: [{ ...search, description: "Tìm" }, create] }), base[1]]],
    ["a tool of another server", [base[0], mcpServer({ name: "wiki", tools: [mcpTool("wiki", "search")] })]],
    ["the server and its tools gone", [base[1]]],
  ])("changes with %s", (_, servers) => {
    expect(handedOut(servers)).not.toBe(handedOut(base));
  });
});

// A server that is tried again is listed with no tool while the agents keep the ones it had,
// and with none still when the try fails: its tools read the same before and after, and only
// the way the try ended says that the agents have lost them.
describe("where the servers stand, as one value", () => {
  const search = mcpTool("notion", "search");
  const wiki = mcpServer({ name: "wiki", tools: [mcpTool("wiki", "read")] });
  const tried = [mcpServer({ status: "idle" }), wiki];

  it.each<[string, McpServerInfo]>([
    ["failed", mcpServer({ status: "failed", error: "connection refused" })],
    ["at a sign-in", mcpServer({ status: "signed_out" })],
    ["connected, with no tool", mcpServer()],
    ["connected, with its tools", mcpServer({ tools: [search] })],
  ])("changes when a try ends %s", (_, ended) => {
    expect(standing([ended, wiki])).not.toBe(standing(tried));
  });

  it.each<[string, McpServerInfo[], McpServerInfo[]]>([
    ["a server with no tool goes down", [mcpServer()], [mcpServer({ status: "failed" })]],
    ["a server that was down asks for a sign-in", [mcpServer({ status: "failed" })], [mcpServer({ status: "signed_out" })]],
    ["a server that was down starts being tried", [mcpServer({ status: "failed" })], [mcpServer({ status: "idle" })]],
    [
      "one try ends as another begins",
      [mcpServer({ status: "idle" }), mcpServer({ name: "wiki", status: "failed" })],
      [mcpServer({ status: "failed" }), mcpServer({ name: "wiki", status: "idle" })],
    ],
    ["a tool comes with no try in between", [mcpServer()], [mcpServer({ tools: [search] })]],
    ["a tool reads another way", [mcpServer({ tools: [search] })], [mcpServer({ tools: [{ ...search, exposure: "direct" }] })]],
  ])("changes when %s", (_, before, after) => {
    expect(standing(after)).not.toBe(standing(before));
  });

  it("stays the same for a list read again, whatever else a server reads as", () => {
    const again = [mcpServer({ status: "idle" }), mcpServer({ name: "wiki", tools: wiki.tools.map((tool) => ({ ...tool })) })];
    expect(standing(again)).toBe(standing(tried));

    const down = mcpServer({ status: "failed", error: "connection refused" });
    const later = { ...down, error: "hết giờ", agents: ["coach"], signed_in: true, description: "Ghi chú" };
    expect(standing([later, wiki])).toBe(standing([down, wiki]));
  });

  // Nothing has been handed out anew before the first try ends, so there is nothing to read.
  it("reads a list in which every server is still being tried like no list at all", () => {
    expect(standing([mcpServer({ status: "idle" }), mcpServer({ name: "wiki", status: "idle" })])).toBe(standing([]));
  });
});

it("hands out the same functions on every render", async () => {
  seed(mcpServer({ status: "idle" }));
  const hook = await opened();
  const first = { ...hook.result.current };

  await pass(2);
  hook.rerender();

  for (const name of ["refresh", "keysChanged", "crewChanged", "reconnect", "signIn", "signOut"] as const) {
    expect(hook.result.current[name], name).toBe(first[name]);
  }
});
