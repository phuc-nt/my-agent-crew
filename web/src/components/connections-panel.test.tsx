import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi as mock } from "vitest";
import { vi } from "../i18n/vi";
import { ConnectionsPanel } from "./connections-panel";
import type { ConnectionsInfo, CredentialInfo, CredentialsInfo } from "../api/types";
import type { CredentialsController } from "../hooks/use-credentials";

const base: ConnectionsInfo = {
  providers: [],
  routes: [],
  vision_routes: [],
  keys: [],
  search_backends: ["duckduckgo"],
  firecrawl_base_url: "",
  telegram: [],
};

const item = (overrides: Partial<CredentialInfo>): CredentialInfo => ({
  name: "OPENROUTER_API_KEY",
  group: "model",
  secret: true,
  url: false,
  present: false,
  source: null,
  checkable: false,
  editable: true,
  ...overrides,
});

function controller(items: CredentialInfo[], overrides: Partial<CredentialsController> = {}) {
  const info: CredentialsInfo = { file: "/h/env", items, restart_required: null };
  return {
    info,
    error: null,
    save: mock.fn(async () => info),
    remove: mock.fn(async () => info),
    check: mock.fn(async () => ({ ok: true, detail: "khoá hợp lệ" })),
    ...overrides,
  } satisfies CredentialsController;
}

describe("ConnectionsPanel", () => {
  it("shows the providers that were built and the routes in order", () => {
    const connections = {
      ...base,
      providers: [
        { name: "openrouter", built: true },
        { name: "ollama", built: true },
      ],
      routes: [
        { provider: "openrouter", model: "gpt-4" },
        { provider: "ollama", model: "qwen" },
      ],
    };
    render(<ConnectionsPanel connections={connections} credentials={controller([])} />);

    expect(screen.getByTestId("providers")).toHaveTextContent("openrouter");
    expect(screen.getByTestId("providers")).toHaveTextContent("ollama");
    expect(screen.getByTestId("routes")).toHaveTextContent("gpt-4");
    expect(screen.getByText(vi.connectionsPage.noVisionRoutes)).toBeInTheDocument();
  });

  it("puts each key on the card of what it connects, with where it is kept", () => {
    const credentials = controller([
      item({ name: "OPENROUTER_API_KEY", present: true, source: "file" }),
      item({ name: "BRAVE_API_KEY", group: "search" }),
      item({ name: "GOODREADS_ID", group: "other", present: true, source: "file" }),
    ]);
    render(<ConnectionsPanel connections={base} credentials={credentials} />);

    expect(screen.getByText(vi.connectionsPage.hint("/h/env"))).toBeInTheDocument();
    expect(screen.getByTestId("credentials-model")).toHaveTextContent("OPENROUTER_API_KEY");
    expect(screen.getByTestId("credentials-search")).toHaveTextContent("BRAVE_API_KEY");
    expect(screen.getByTestId("credentials-other")).toHaveTextContent("GOODREADS_ID");
    const set = within(screen.getByTestId("credential-BRAVE_API_KEY"));
    expect(set.getByText(vi.connectionsPage.absent)).toBeInTheDocument();
    expect(set.getByRole("button", { name: vi.connectionsPage.set })).toBeInTheDocument();
  });

  it("saves a key through a password field that is empty again afterwards", async () => {
    const credentials = controller([item({})]);
    render(<ConnectionsPanel connections={base} credentials={credentials} />);
    const row = within(screen.getByTestId("credential-OPENROUTER_API_KEY"));

    fireEvent.click(row.getByRole("button", { name: vi.connectionsPage.set }));
    const field = row.getByLabelText(vi.connectionsPage.valueFor("OPENROUTER_API_KEY"));
    expect(field).toHaveAttribute("type", "password");
    fireEvent.change(field, { target: { value: "sk-or-v1-abc" } });
    fireEvent.click(row.getByRole("button", { name: vi.connectionsPage.save }));

    await waitFor(() => expect(row.getByRole("status")).toHaveTextContent(vi.connectionsPage.saved));
    expect(credentials.save).toHaveBeenCalledWith("OPENROUTER_API_KEY", "sk-or-v1-abc");
    expect(row.queryByLabelText(vi.connectionsPage.valueFor("OPENROUTER_API_KEY"))).toBeNull();
    expect(screen.getByTestId("connections").innerHTML).not.toContain("sk-or-v1-abc");
  });

  it("says why a save was refused", async () => {
    const credentials = controller([item({})], {
      save: mock.fn(async () => {
        throw new Error("Giá trị không được xuống dòng.");
      }),
    });
    render(<ConnectionsPanel connections={base} credentials={credentials} />);
    const row = within(screen.getByTestId("credential-OPENROUTER_API_KEY"));

    fireEvent.click(row.getByRole("button", { name: vi.connectionsPage.set }));
    fireEvent.change(row.getByLabelText(vi.connectionsPage.valueFor("OPENROUTER_API_KEY")), {
      target: { value: "x" },
    });
    fireEvent.click(row.getByRole("button", { name: vi.connectionsPage.save }));

    await waitFor(() => expect(row.getByRole("status")).toHaveTextContent("xuống dòng"));
  });

  it("checks a key and removes one only after confirming", async () => {
    const credentials = controller([
      item({ present: true, source: "file", checkable: true }),
    ]);
    render(<ConnectionsPanel connections={base} credentials={credentials} />);
    const row = within(screen.getByTestId("credential-OPENROUTER_API_KEY"));

    fireEvent.click(row.getByRole("button", { name: vi.connectionsPage.check }));
    await waitFor(() => expect(row.getByRole("status")).toHaveTextContent("khoá hợp lệ"));

    const confirm = mock.spyOn(window, "confirm").mockReturnValueOnce(false);
    fireEvent.click(row.getByRole("button", { name: vi.connectionsPage.remove }));
    expect(credentials.remove).not.toHaveBeenCalled();
    confirm.mockReturnValueOnce(true);
    fireEvent.click(row.getByRole("button", { name: vi.connectionsPage.remove }));
    await waitFor(() => expect(credentials.remove).toHaveBeenCalledWith("OPENROUTER_API_KEY"));
    confirm.mockRestore();
  });

  it("offers no removal for a key the server was started with", () => {
    const credentials = controller([item({ present: true, source: "process" })]);
    render(<ConnectionsPanel connections={base} credentials={credentials} />);
    const row = within(screen.getByTestId("credential-OPENROUTER_API_KEY"));

    expect(row.queryByRole("button", { name: vi.connectionsPage.remove })).toBeNull();
    expect(row.getByText(vi.connectionsPage.fromProcess)).toBeInTheDocument();
  });

  it("offers no controls for a name only the file itself can change", () => {
    const credentials = controller([
      item({ name: "lower_case", group: "other", present: true, source: "file", editable: false }),
    ]);
    render(<ConnectionsPanel connections={base} credentials={credentials} />);
    const row = within(screen.getByTestId("credential-lower_case"));

    expect(row.queryByRole("button")).toBeNull();
    expect(row.getByText(vi.connectionsPage.fileOnly)).toBeInTheDocument();
  });

  it("shows a host address and its default, since they are not secrets", () => {
    const credentials = controller([
      item({ name: "OLLAMA_BASE_URL", secret: false, url: true, value: "", default: "http://127.0.0.1:11434/v1" }),
      item({ name: "FIRECRAWL_BASE_URL", group: "search", secret: false, url: true, present: true, source: "file", value: "http://127.0.0.1:3002" }),
    ]);
    render(<ConnectionsPanel connections={base} credentials={credentials} />);

    expect(screen.getByTestId("credential-OLLAMA_BASE_URL")).toHaveTextContent("Mặc định: http://127.0.0.1:11434/v1");
    expect(screen.getByTestId("credential-FIRECRAWL_BASE_URL")).toHaveTextContent("http://127.0.0.1:3002");
  });

  it("adds a variable of the person's own, upper-casing the name as it is typed", async () => {
    const credentials = controller([]);
    render(<ConnectionsPanel connections={base} credentials={credentials} />);
    const form = within(screen.getByTestId("credential-add"));
    const add = form.getByRole("button", { name: vi.connectionsPage.add });

    fireEvent.change(form.getByLabelText(vi.connectionsPage.newName), { target: { value: "1bad" } });
    expect(form.getByText(vi.connectionsPage.nameRule)).toBeInTheDocument();
    fireEvent.change(form.getByLabelText(vi.connectionsPage.newName), { target: { value: "goodreads_id" } });
    fireEvent.change(form.getByLabelText(vi.connectionsPage.valueFor("GOODREADS_ID")), { target: { value: "42" } });
    expect(add).toBeEnabled();
    fireEvent.click(add);

    await waitFor(() => expect(credentials.save).toHaveBeenCalledWith("GOODREADS_ID", "42"));
  });

  it("names the bot token under Telegram with the agent that uses it", () => {
    const connections = {
      ...base,
      telegram: [{ agent_id: "default", token_env: "CREW_BOT", configured: true, ignored: false }],
    };
    const credentials = controller([
      item({ name: "CREW_BOT", group: "telegram", present: true, source: "file", agents: ["default"] }),
    ]);
    render(<ConnectionsPanel connections={connections} credentials={credentials} />);

    expect(screen.getByTestId("telegram-list")).toHaveTextContent("CREW_BOT");
    expect(screen.getByTestId("credentials-telegram")).toHaveTextContent(vi.connectionsPage.usedBy("default"));
  });

  it("explains how to turn Telegram on when no agent has it", () => {
    render(<ConnectionsPanel connections={base} credentials={controller([])} />);

    expect(screen.getByText(vi.connectionsPage.noTelegram)).toBeInTheDocument();
  });

  it("says the list could not load instead of showing no keys", () => {
    const credentials = { ...controller([]), info: null, error: "HTTP 403" };
    render(<ConnectionsPanel connections={base} credentials={credentials} />);

    expect(screen.getByText("HTTP 403")).toBeInTheDocument();
    expect(screen.queryByTestId("credential-add")).toBeNull();
  });
});
