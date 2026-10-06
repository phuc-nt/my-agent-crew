import { describe, expect, it } from "vitest";
import { FakeMcp, SIGN_IN_LOCAL_ONLY, authorizeUrl, mcpServer, mcpTool, scriptTool, searchTool, unknownServer } from "./fake-mcp";

type Listed = { servers: ReturnType<typeof mcpServer>[] };
const list = (mcp: FakeMcp) => (mcp.route("/mcp", "GET")?.body as Listed).servers;

describe("the MCP routes both fakes answer", () => {
  it("names a tool the way the crew does: server, then what the server calls it, made safe", () => {
    expect(mcpTool("notion", "create-page").name).toBe("mcp__notion__create_page");
    expect(mcpTool("notion", "create-page").remote).toBe("create-page");
    expect(mcpTool("notion", "search")).toMatchObject({ exposure: "deferred", requires_approval: true });
  });

  it("lists the servers, and reads who uses each off the crew when it has one", () => {
    const mcp = new FakeMcp([mcpServer({ agents: ["seeded"] }), mcpServer({ name: "wiki" })]);
    expect(list(mcp).map((s) => s.agents)).toEqual([["seeded"], []]);

    mcp.crew = () => [{ id: "default", mcp: ["wiki", "notion"] }, { id: "coach", mcp: ["notion"] }, { id: "old" }];
    expect(list(mcp).map((s) => s.agents)).toEqual([["coach", "default"], ["default"]]);
  });

  it("answers 404 in the server's words for a name the file does not declare", () => {
    const mcp = new FakeMcp([mcpServer()]);

    for (const [path, method] of [["/mcp/ghost/reconnect", "POST"], ["/mcp/ghost/login", "POST"], ["/mcp/ghost/login", "DELETE"]]) {
      expect(mcp.route(path, method)).toEqual({ status: 404, body: { detail: "Không có máy chủ MCP tên ghost." } });
    }
  });

  it("leaves every other path to the fake it sits in", () => {
    const mcp = new FakeMcp([mcpServer()]);

    expect(mcp.route("/tools", "GET")).toBeNull();
    expect(mcp.route("/mcp", "POST")).toBeNull();
    expect(mcp.route("/mcp/notion/reconnect", "GET")).toBeNull();
    expect(mcp.route("/mcp/notion/tools", "GET")).toBeNull();
  });

  it("finds a server as the test said it would be when it is tried again, once", () => {
    const mcp = new FakeMcp([mcpServer({ status: "failed", error: "HTTP 503" })]);
    mcp.becomes("notion", { status: "connected", error: "" });

    expect((mcp.route("/mcp/notion/reconnect", "POST")?.body as Listed).servers[0]).toMatchObject({ status: "connected", error: "" });

    mcp.servers = [mcpServer({ status: "failed" })];
    expect((mcp.route("/mcp/notion/reconnect", "POST")?.body as Listed).servers[0].status).toBe("failed");
  });

  it("tries the servers that wait when a key changes, and leaves alone one that wants a sign-in", () => {
    const mcp = new FakeMcp([
      mcpServer({ name: "down", status: "failed" }),
      mcpServer({ name: "trying", status: "idle" }),
      mcpServer({ name: "locked", status: "signed_out" }),
    ]);
    for (const name of ["down", "trying", "locked"]) mcp.becomes(name, { status: "connected" });

    mcp.wake();

    expect(list(mcp).map((s) => s.status)).toEqual(["connected", "connected", "signed_out"]);
  });

  it("answers a sign-in with the address to go to, or refuses once in the words it was given", () => {
    const mcp = new FakeMcp([mcpServer({ name: "my wiki", status: "signed_out" })]);
    mcp.refuseSignIn = SIGN_IN_LOCAL_ONLY;

    expect(mcp.route("/mcp/my%20wiki/login", "POST")).toEqual({ status: 409, body: { detail: SIGN_IN_LOCAL_ONLY } });
    expect(mcp.route("/mcp/my%20wiki/login", "POST")).toEqual({ status: 200, body: { authorize_url: authorizeUrl("my wiki") } });
    expect(authorizeUrl("my wiki")).toBe("https://auth.example.test/authorize?server=my%20wiki");
  });

  it("connects a server the person signed in to, and empties one they signed out of", () => {
    const mcp = new FakeMcp([mcpServer({ status: "signed_out", error: "sign-in ran out" }), mcpServer({ name: "wiki" })]);

    mcp.signedIn("notion", [mcpTool("notion", "search")]);
    expect(list(mcp)[0]).toMatchObject({ status: "connected", signed_in: true, error: "" });
    expect(list(mcp)[0].tools).toHaveLength(1);

    const after = (mcp.route("/mcp/notion/login", "DELETE")?.body as Listed).servers;
    expect(after[0]).toMatchObject({ status: "signed_out", signed_in: false, error: "", tools: [], skipped: [] });
    expect(after[1].status).toBe("connected");
  });

  it("adds to the tool list only what an agent holds: no hidden tool, no server nobody uses", () => {
    const tools = [mcpTool("notion", "search", { requires_approval: false }), mcpTool("notion", "purge", { exposure: "hidden" })];
    const mcp = new FakeMcp([mcpServer({ tools }), mcpServer({ name: "wiki", tools: [mcpTool("wiki", "read")] })]);
    mcp.crew = () => [{ id: "default", mcp: ["notion"] }];

    expect(mcp.registryTools()).toEqual([
      searchTool(["default"]),
      {
        name: "mcp__notion__search",
        description: "",
        requires_approval: false,
        agents: ["default"],
        optional: false,
        server: "notion",
        exposure: "deferred",
      },
    ]);
  });

  it("lists the search for the agents that hold a tool not declared up front, and only then", () => {
    const direct = mcpServer({ name: "wiki", tools: [mcpTool("wiki", "read", { exposure: "direct" }), mcpTool("wiki", "purge", { exposure: "hidden" })] });
    const scripted = mcpServer({ name: "tracker", tools: [mcpTool("tracker", "list", { exposure: "codemode" })] });
    const mcp = new FakeMcp([direct, mcpServer({ tools: [mcpTool("notion", "search")] }), scripted]);
    let crew = [{ id: "default", mcp: ["wiki"] }, { id: "coach" }];
    mcp.crew = () => crew;
    const names = () => mcp.registryTools().map((tool) => tool.name);

    // Every tool the one agent holds is declared to the model: there is nothing to find.
    expect(names()).toEqual(["mcp__wiki__read"]);

    crew = [{ id: "ledger", mcp: ["tracker"] }, { id: "default", mcp: ["wiki", "notion"] }, { id: "coach" }];
    const [search, ...rest] = mcp.registryTools();
    expect(search).toEqual({ ...searchTool(["default", "ledger"]), with_mcp: true, requires_approval: false, optional: false });
    expect(search).not.toHaveProperty("server");
    expect(rest.map((tool) => tool.name)).toEqual(["mcp__wiki__read", "mcp__notion__search", "mcp__tracker__list"]);
    expect(rest.every((tool) => !("with_mcp" in tool))).toBe(true);
  });

  it("lists the script tool for the agents with a tool that only reads and is opened for scripts", () => {
    const reads = { requires_approval: false };
    const tracker = mcpServer({
      name: "tracker",
      tools: [mcpTool("tracker", "list", { exposure: "codemode", ...reads }), mcpTool("tracker", "close", { exposure: "codemode" })],
    });
    // Neither of these opens a script: one asks first, the other is not opened for scripts.
    const asks = mcpServer({ name: "wiki", tools: [mcpTool("wiki", "edit", { exposure: "codemode" })] });
    const plain = mcpServer({ tools: [mcpTool("notion", "search", reads), mcpTool("notion", "fetch", { exposure: "direct", ...reads })] });
    const mcp = new FakeMcp([asks, plain, tracker]);
    let crew = [{ id: "default", mcp: ["wiki", "notion"] }, { id: "coach" }];
    mcp.crew = () => crew;
    const names = () => mcp.registryTools().map((tool) => tool.name);

    expect(names()).toEqual(["tool_search", "mcp__wiki__edit", "mcp__notion__search", "mcp__notion__fetch"]);

    crew = [{ id: "ledger", mcp: ["tracker"] }, { id: "default", mcp: ["wiki", "tracker"] }, { id: "coach", mcp: ["notion"] }];
    const [search, script, ...rest] = mcp.registryTools();
    expect(search).toEqual(searchTool(["coach", "default", "ledger"]));
    // The coach can find tools and call none from a script.
    expect(script).toEqual(scriptTool(["default", "ledger"]));
    expect(script).toMatchObject({ name: "tool_script", with_mcp: true, requires_approval: false, optional: false });
    expect(script).not.toHaveProperty("server");
    expect(rest.map((tool) => tool.name)).toEqual([
      "mcp__wiki__edit",
      "mcp__notion__search",
      "mcp__notion__fetch",
      "mcp__tracker__list",
      "mcp__tracker__close",
    ]);
    expect(rest.every((tool) => !("with_mcp" in tool))).toBe(true);
  });

  it("names who holds the script tool in the order of their names, whichever server opened it first", () => {
    const opened = { exposure: "codemode", requires_approval: false } as const;
    const mcp = new FakeMcp([
      mcpServer({ name: "board", tools: [mcpTool("board", "read", opened)] }),
      mcpServer({ name: "tracker", tools: [mcpTool("tracker", "list", opened)] }),
    ]);
    // The first server is the one the later name holds.
    mcp.crew = () => [{ id: "ledger", mcp: ["board"] }, { id: "default", mcp: ["tracker"] }];

    const [search, script] = mcp.registryTools();

    expect(search).toEqual(searchTool(["default", "ledger"]));
    expect(script).toEqual(scriptTool(["default", "ledger"]));
  });

  it("opens no script for a tool that is hidden, or for a server nobody uses", () => {
    const hidden = mcpTool("notion", "purge", { exposure: "hidden", requires_approval: false });
    const mcp = new FakeMcp([
      mcpServer({ tools: [hidden, mcpTool("notion", "create-page", { exposure: "direct" })] }),
      mcpServer({ name: "tracker", tools: [mcpTool("tracker", "list", { exposure: "codemode", requires_approval: false })] }),
    ]);
    mcp.crew = () => [{ id: "default", mcp: ["notion"] }];

    expect(mcp.registryTools().map((tool) => tool.name)).toEqual(["mcp__notion__create_page"]);
  });

  it("refuses an agent's list that names a server the file does not declare", () => {
    const mcp = new FakeMcp([mcpServer()]);

    expect(mcp.refusal(["notion"])).toBeNull();
    expect(mcp.refusal([])).toBeNull();
    expect(mcp.refusal(null)).toBeNull();
    expect(mcp.refusal(["notion", "old"])).toBe(unknownServer("old"));
    expect(unknownServer("old")).toBe("Không có máy chủ MCP tên old trong config.yaml.");
  });
});
