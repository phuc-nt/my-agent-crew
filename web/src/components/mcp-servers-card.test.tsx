import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi as mock } from "vitest";
import { ApiError } from "../api/client";
import type { McpServerInfo } from "../api/types";
import type { McpController } from "../hooks/use-mcp-servers";
import { vi } from "../i18n/vi";
import { SIGN_IN_LOCAL_ONLY, mcpServer, mcpTool } from "../test/fake-mcp";
import { McpServerList } from "./mcp-servers-card";

const t = vi.mcp;

function controller(servers: McpServerInfo[], overrides: Partial<McpController> = {}): McpController {
  return {
    servers,
    error: null,
    refresh: mock.fn(async () => undefined),
    keysChanged: mock.fn(async () => undefined),
    reconnect: mock.fn(async () => undefined),
    signIn: mock.fn(async () => undefined),
    signOut: mock.fn(async () => undefined),
    ...overrides,
  };
}

const show = (servers: McpServerInfo[], overrides: Partial<McpController> = {}) => {
  const mcp = controller(servers, overrides);
  render(<McpServerList mcp={mcp} />);
  return mcp;
};
const row = (name = "notion") => within(screen.getByTestId(`mcp-server-${name}`));
const button = (label: string, name = "notion") => row(name).queryByRole("button", { name: label });

/** A request that waits for the test to let it end. */
function held() {
  let release: (error?: unknown) => void = () => {};
  const work = new Promise<void>((resolve, reject) => {
    release = (error) => (error === undefined ? resolve() : reject(error));
  });
  return { work, release };
}

afterEach(() => mock.restoreAllMocks());

describe("the list of MCP servers", () => {
  it("says how to declare a server when the file names none", () => {
    show([]);

    expect(screen.getByText(t.empty)).toBeInTheDocument();
    expect(screen.queryByTestId("mcp-servers")).not.toBeInTheDocument();
  });

  it("says the list could not be read, in place of claiming there are no servers", () => {
    show([], { error: vi.requestErrors.network });

    expect(screen.getByRole("status")).toHaveTextContent(t.loadFailed(vi.requestErrors.network));
    expect(screen.queryByText(t.empty)).not.toBeInTheDocument();
  });

  it("keeps showing the servers it has when a later read fails", () => {
    show([mcpServer()], { error: vi.requestErrors.network });

    expect(screen.getByTestId("mcp-server-notion")).toBeInTheDocument();
    expect(screen.queryByText(t.loadFailed(vi.requestErrors.network))).not.toBeInTheDocument();
  });

  it.each([
    ["connected", "ok"],
    ["idle", "warn"],
    ["signed_out", "warn"],
    ["failed", "danger"],
  ] as const)("words a server that is %s and colours it %s", (status, tone) => {
    show([mcpServer({ status })]);

    const badge = row().getByTestId("mcp-status");
    expect(badge).toHaveTextContent(t.status[status]);
    expect(badge).toHaveClass("badge", tone);
  });

  it("shows where the server is, what it is for and why it is down", () => {
    show([mcpServer({ status: "failed", description: "Ghi chú của nhà", error: "notion: HTTP 503" })]);

    expect(row().getByText("https://mcp.notion.com/mcp")).toBeInTheDocument();
    expect(row().getByText("Ghi chú của nhà")).toBeInTheDocument();
    expect(row().getByTestId("mcp-error")).toHaveTextContent("notion: HTTP 503");
  });

  // The crew keeps the last try's reason while it tries again, and so does the row: the
  // reason is what says why a server reads "connecting" long after the crew started.
  it("keeps the reason of the last try while the server is being tried again", () => {
    show([mcpServer({ status: "idle", error: "notion: HTTP 503" })]);

    expect(row().getByTestId("mcp-status")).toHaveTextContent(t.status.idle);
    expect(row().getByTestId("mcp-error")).toHaveTextContent("notion: HTTP 503");
  });

  it("shows no reason for a server that has none", () => {
    show([mcpServer()]);

    expect(row().queryByTestId("mcp-error")).not.toBeInTheDocument();
  });

  it("names the agents that use a server, or says how to hand it to one", () => {
    show([mcpServer({ agents: ["coach", "default"] }), mcpServer({ name: "wiki" })]);

    expect(row().getByTestId("mcp-agents")).toHaveTextContent(vi.connectionsPage.usedBy("coach, default"));
    expect(row("wiki").getByTestId("mcp-agents")).toHaveTextContent(t.noAgents);
  });

  it("marks a server signed in to, and one that reads its key from a header", () => {
    show([mcpServer({ signed_in: true }), mcpServer({ name: "wiki", uses_key: true })]);

    expect(row().getByText(t.signedIn)).toBeInTheDocument();
    expect(row().queryByText(t.usesKey)).not.toBeInTheDocument();
    expect(row("wiki").getByText(t.usesKey)).toBeInTheDocument();
    expect(row("wiki").queryByText(t.signedIn)).not.toBeInTheDocument();
  });
});

describe("the tools of a server", () => {
  const tools = [
    mcpTool("notion", "search", { description: "Tìm trang", requires_approval: false, read_only_hint: true }),
    mcpTool("notion", "create-page", { exposure: "direct" }),
    mcpTool("notion", "purge", { exposure: "hidden" }),
  ];

  it("are counted, and listed under the name the server gives them", () => {
    show([mcpServer({ tools })]);

    expect(row().getByText(t.tools(3))).toBeInTheDocument();
    expect(within(row().getByTestId("mcp-tool-create-page")).getByText("create-page")).toBeInTheDocument();
    expect(row().getByTestId("mcp-tool-search")).toHaveTextContent("Tìm trang");
  });

  it("say which ask before they run, by the crew's rule and not the server's word", () => {
    show([mcpServer({ tools })]);

    const search = within(row().getByTestId("mcp-tool-search"));
    expect(search.getByText(t.runsFreely)).toHaveClass("badge", "ok");
    expect(search.queryByText(t.asksFirst)).not.toBeInTheDocument();
    expect(search.getByText(t.saysReadOnly)).toHaveAttribute("title", t.saysReadOnlyTitle);

    const create = within(row().getByTestId("mcp-tool-create-page"));
    expect(create.getByText(t.asksFirst)).toHaveClass("badge", "warn");
    expect(create.queryByText(t.runsFreely)).not.toBeInTheDocument();
    expect(create.queryByText(t.saysReadOnly)).not.toBeInTheDocument();
  });

  it("say how each reaches an agent", () => {
    show([mcpServer({ tools })]);

    const badge = (remote: string, label: string) => within(row().getByTestId(`mcp-tool-${remote}`)).getByText(label);
    expect(badge("search", t.exposure.deferred)).toHaveAttribute("title", t.exposureTitle.deferred);
    expect(badge("create-page", t.exposure.direct)).toHaveAttribute("title", t.exposureTitle.direct);
    expect(badge("purge", t.exposure.hidden)).toHaveAttribute("title", t.exposureTitle.hidden);
  });

  it("are left out for a server that offers none, and the ones passed over are named", () => {
    show([mcpServer({ skipped: ["search", "fetch"] })]);

    expect(row().queryByText(t.tools(0))).not.toBeInTheDocument();
    expect(row().getByText(t.skipped("search, fetch"))).toBeInTheDocument();
  });

  it("name nothing as passed over when nothing was", () => {
    show([mcpServer({ tools })]);

    expect(row().queryByText(/Bỏ qua/)).not.toBeInTheDocument();
  });
});

describe("what can be done with a server", () => {
  it("offers a sign-in only to a server that waits for one", () => {
    show([
      mcpServer({ status: "signed_out" }),
      mcpServer({ name: "up" }),
      mcpServer({ name: "down", status: "failed" }),
      mcpServer({ name: "trying", status: "idle" }),
    ]);

    expect(button(t.signIn)).toBeInTheDocument();
    expect(row().getByText(t.signInHint)).toBeInTheDocument();
    for (const name of ["up", "down", "trying"]) {
      expect(button(t.signIn, name), name).not.toBeInTheDocument();
      expect(row(name).queryByText(t.signInHint), name).not.toBeInTheDocument();
      expect(button(t.reconnect, name), name).toBeInTheDocument();
    }
  });

  it("offers a sign-out only where there is a sign-in to drop", () => {
    show([mcpServer({ signed_in: true }), mcpServer({ name: "wiki", uses_key: true })]);

    expect(button(t.signOut)).toBeInTheDocument();
    expect(button(t.signOut, "wiki")).not.toBeInTheDocument();
  });

  it("tries the server again, holding every control until the answer is in", async () => {
    const { work, release } = held();
    const mcp = show([mcpServer({ status: "signed_out", signed_in: true })], { reconnect: mock.fn(() => work) });

    await userEvent.click(button(t.reconnect)!);

    expect(mcp.reconnect).toHaveBeenCalledWith("notion");
    expect(button(t.reconnecting)).toBeDisabled();
    expect(button(t.signIn)).toBeDisabled();
    expect(button(t.signOut)).toBeDisabled();

    release();
    await waitFor(() => expect(button(t.reconnect)).toBeEnabled());
    expect(button(t.signIn)).toBeEnabled();
    expect(button(t.signOut)).toBeEnabled();
    // The row's own state says how it went; a note would only say it was tried.
    expect(row().queryByTestId("mcp-note")).not.toBeInTheDocument();
  });

  it("holds only the controls of the server being worked on", async () => {
    const { work, release } = held();
    show([mcpServer(), mcpServer({ name: "wiki" })], { reconnect: mock.fn(() => work) });

    await userEvent.click(button(t.reconnect)!);

    expect(button(t.reconnect, "wiki")).toBeEnabled();
    release();
    await waitFor(() => expect(button(t.reconnect)).toBeEnabled());
  });

  it("puts the server's refusal in words under the row", async () => {
    const refused = new ApiError(404, "Không có máy chủ MCP tên notion.");
    show([mcpServer()], { reconnect: mock.fn(async () => Promise.reject(refused)) });

    await userEvent.click(button(t.reconnect)!);

    const note = await row().findByTestId("mcp-note");
    expect(note).toHaveTextContent(vi.connectionsPage.failed("Không có máy chủ MCP tên notion."));
    expect(note).toHaveClass("danger");
    expect(button(t.reconnect)).toBeEnabled();
  });

  it("starts a sign-in, saying so while the page is on its way out", async () => {
    const { work, release } = held();
    const mcp = show([mcpServer({ status: "signed_out" })], { signIn: mock.fn(() => work) });

    await userEvent.click(button(t.signIn)!);

    expect(mcp.signIn).toHaveBeenCalledWith("notion");
    expect(button(t.signingIn)).toBeDisabled();
    expect(button(t.reconnect)).toBeDisabled();
    release();
    await waitFor(() => expect(button(t.signIn)).toBeEnabled());
  });

  it("says why a sign-in could not start from this browser", async () => {
    const refused = new ApiError(409, SIGN_IN_LOCAL_ONLY);
    show([mcpServer({ status: "signed_out" })], { signIn: mock.fn(async () => Promise.reject(refused)) });

    await userEvent.click(button(t.signIn)!);

    expect(await row().findByTestId("mcp-note")).toHaveTextContent(SIGN_IN_LOCAL_ONLY);
    expect(button(t.signIn)).toBeEnabled();
  });

  it("drops a note once the next action starts", async () => {
    const reconnect = mock
      .fn<McpController["reconnect"]>()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValue(undefined);
    show([mcpServer()], { reconnect });

    await userEvent.click(button(t.reconnect)!);
    expect(await row().findByTestId("mcp-note")).toHaveTextContent(vi.connectionsPage.failed(vi.requestErrors.network));

    await userEvent.click(button(t.reconnect)!);
    await waitFor(() => expect(row().queryByTestId("mcp-note")).not.toBeInTheDocument());
  });

  it("signs out only once the person has agreed to", async () => {
    const confirm = mock.spyOn(window, "confirm").mockReturnValue(false);
    const mcp = show([mcpServer({ signed_in: true })]);

    await userEvent.click(button(t.signOut)!);

    expect(confirm).toHaveBeenCalledWith(t.confirmSignOut("notion"));
    expect(mcp.signOut).not.toHaveBeenCalled();
    expect(row().queryByTestId("mcp-note")).not.toBeInTheDocument();

    confirm.mockReturnValue(true);
    await userEvent.click(button(t.signOut)!);

    expect(mcp.signOut).toHaveBeenCalledWith("notion");
    const note = await row().findByTestId("mcp-note");
    expect(note).toHaveTextContent(t.signedOut);
    expect(note).toHaveClass("ok");
  });

  it("says a sign-out is under way, holding every control until it is done", async () => {
    mock.spyOn(window, "confirm").mockReturnValue(true);
    const { work, release } = held();
    show([mcpServer({ signed_in: true })], { signOut: mock.fn(() => work) });

    await userEvent.click(button(t.signOut)!);

    expect(button(t.signingOut)).toBeDisabled();
    expect(button(t.signOut)).not.toBeInTheDocument();
    expect(button(t.reconnect)).toBeDisabled();

    release();
    await waitFor(() => expect(button(t.signOut)).toBeEnabled());
    expect(button(t.signingOut)).not.toBeInTheDocument();
  });

  it("says a sign-out failed, and does not say it went through", async () => {
    mock.spyOn(window, "confirm").mockReturnValue(true);
    show([mcpServer({ signed_in: true })], { signOut: mock.fn(async () => Promise.reject(new ApiError(500, "boom"))) });

    await userEvent.click(button(t.signOut)!);

    const note = await row().findByTestId("mcp-note");
    expect(note).toHaveTextContent(vi.connectionsPage.failed(vi.requestErrors.server(500)));
    expect(note).not.toHaveTextContent(t.signedOut);
  });
});
