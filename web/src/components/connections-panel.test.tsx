import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { vi } from "../i18n/vi";
import { ConnectionsPanel } from "./connections-panel";
import type { ConnectionsInfo } from "../api/types";

describe("ConnectionsPanel", () => {
  it("renders the providers section with all providers", () => {
    const connections: ConnectionsInfo = {
      providers: [
        { name: "openai", built: true },
        { name: "anthropic", built: true },
      ],
      routes: [],
      vision_routes: [],
      keys: [],
      search_backends: ["duckduckgo"],
      firecrawl_base_url: "",
      telegram: [],
    };
    render(<ConnectionsPanel connections={connections} />);

    expect(screen.getByText(vi.connectionsPage.providers)).toBeInTheDocument();
    expect(screen.getByText("openai")).toBeInTheDocument();
    expect(screen.getByText("anthropic")).toBeInTheDocument();
  });

  it("says where ollama is looked for so a dead one is told from a wrong host", () => {
    const connections: ConnectionsInfo = {
      providers: [{ name: "ollama", built: true }],
      routes: [],
      vision_routes: [],
      keys: [],
      search_backends: ["duckduckgo"],
      firecrawl_base_url: "",
      ollama_base_url: "http://127.0.0.1:11434/v1",
      telegram: [],
    };
    render(<ConnectionsPanel connections={connections} />);

    expect(screen.getByTestId("ollama-base-url")).toHaveTextContent("http://127.0.0.1:11434/v1");
  });

  it("leaves the ollama line out when the server did not report an address", () => {
    const connections: ConnectionsInfo = {
      providers: [],
      routes: [],
      vision_routes: [],
      keys: [],
      search_backends: ["duckduckgo"],
      firecrawl_base_url: "",
      telegram: [],
    };
    render(<ConnectionsPanel connections={connections} />);

    expect(screen.queryByTestId("ollama-base-url")).toBeNull();
  });

  it("renders the routes section with model routes", () => {
    const connections: ConnectionsInfo = {
      providers: [],
      routes: [
        { provider: "openai", model: "gpt-4" },
        { provider: "anthropic", model: "claude-3-opus" },
      ],
      vision_routes: [],
      keys: [],
      search_backends: ["duckduckgo"],
      firecrawl_base_url: "",
      telegram: [],
    };
    render(<ConnectionsPanel connections={connections} />);

    expect(screen.getByText(vi.connectionsPage.routes)).toBeInTheDocument();
    expect(screen.getByText("openai")).toBeInTheDocument();
    expect(screen.getByText("gpt-4")).toBeInTheDocument();
    expect(screen.getByText("claude-3-opus")).toBeInTheDocument();
  });

  it("renders the vision routes section when routes are present", () => {
    const connections: ConnectionsInfo = {
      providers: [],
      routes: [],
      vision_routes: [
        { provider: "openai", model: "gpt-4-vision" },
      ],
      keys: [],
      search_backends: ["duckduckgo"],
      firecrawl_base_url: "",
      telegram: [],
    };
    render(<ConnectionsPanel connections={connections} />);

    expect(screen.getByText(vi.connectionsPage.visionRoutes)).toBeInTheDocument();
    expect(screen.getByText("gpt-4-vision")).toBeInTheDocument();
  });

  it("shows the no vision routes message when there are none", () => {
    const connections: ConnectionsInfo = {
      providers: [],
      routes: [],
      vision_routes: [],
      keys: [],
      search_backends: ["duckduckgo"],
      firecrawl_base_url: "",
      telegram: [],
    };
    render(<ConnectionsPanel connections={connections} />);

    expect(screen.getByText(vi.connectionsPage.noVisionRoutes)).toBeInTheDocument();
  });

  it("renders the keys section showing present and absent keys", () => {
    const connections: ConnectionsInfo = {
      providers: [],
      routes: [],
      vision_routes: [],
      keys: [
        { name: "OPENAI_API_KEY", present: true },
        { name: "BRAVE_API_KEY", present: false },
      ],
      search_backends: ["duckduckgo"],
      firecrawl_base_url: "",
      telegram: [],
    };
    render(<ConnectionsPanel connections={connections} />);

    expect(screen.getByText(vi.connectionsPage.keys)).toBeInTheDocument();
    expect(screen.getByText("OPENAI_API_KEY")).toBeInTheDocument();
    expect(screen.getByText("BRAVE_API_KEY")).toBeInTheDocument();
    expect(screen.getByText(vi.connectionsPage.present)).toBeInTheDocument();
    expect(screen.getByText(vi.connectionsPage.absent)).toBeInTheDocument();
  });

  it("PRIVACY: does NOT render the actual API key value", () => {
    const connections: ConnectionsInfo = {
      providers: [],
      routes: [],
      vision_routes: [],
      keys: [
        { name: "OPENAI_API_KEY", present: true },
      ],
      search_backends: ["duckduckgo"],
      firecrawl_base_url: "",
      telegram: [],
    };
    render(<ConnectionsPanel connections={connections} />);

    // The env var NAME should be shown
    expect(screen.getByText("OPENAI_API_KEY")).toBeInTheDocument();
    // But never the actual secret value
    const text = screen.getByTestId("keys").textContent;
    expect(text).not.toMatch(/sk-[a-zA-Z0-9]/);
  });

  it("shows the Telegram section when channels are configured", () => {
    const connections: ConnectionsInfo = {
      providers: [],
      routes: [],
      vision_routes: [],
      keys: [],
      search_backends: ["duckduckgo"],
      firecrawl_base_url: "",
      telegram: [
        { agent_id: "coach", token_env: "COACH_TOKEN", configured: true, ignored: false },
      ],
    };
    render(<ConnectionsPanel connections={connections} />);

    expect(screen.getByText(vi.connectionsPage.telegram)).toBeInTheDocument();
    expect(screen.getByText("coach")).toBeInTheDocument();
    expect(screen.getByText("COACH_TOKEN")).toBeInTheDocument();
  });

  it("shows the no telegram message when no channels are configured", () => {
    const connections: ConnectionsInfo = {
      providers: [],
      routes: [],
      vision_routes: [],
      keys: [],
      search_backends: ["duckduckgo"],
      firecrawl_base_url: "",
      telegram: [],
    };
    render(<ConnectionsPanel connections={connections} />);

    expect(screen.getByText(vi.connectionsPage.noTelegram)).toBeInTheDocument();
  });

  it("PRIVACY: shows only the token env NAME, never the token value for Telegram", () => {
    const connections: ConnectionsInfo = {
      providers: [],
      routes: [],
      vision_routes: [],
      keys: [],
      search_backends: ["duckduckgo"],
      firecrawl_base_url: "",
      telegram: [
        { agent_id: "coach", token_env: "COACH_TOKEN", configured: true, ignored: false },
      ],
    };
    render(<ConnectionsPanel connections={connections} />);

    const telegramList = screen.getByTestId("telegram-list");
    const text = telegramList.textContent;

    // The env var NAME should be shown
    expect(text).toContain("COACH_TOKEN");
    // But never an actual token value
    expect(text).not.toMatch(/\d{10,}/);
  });

  it("marks configured Telegram channels with ok badge", () => {
    const connections: ConnectionsInfo = {
      providers: [],
      routes: [],
      vision_routes: [],
      keys: [],
      search_backends: ["duckduckgo"],
      firecrawl_base_url: "",
      telegram: [
        { agent_id: "coach", token_env: "COACH_TOKEN", configured: true, ignored: false },
        { agent_id: "coder", token_env: "CODER_TOKEN", configured: false, ignored: false },
      ],
    };
    render(<ConnectionsPanel connections={connections} />);

    const badges = screen.getAllByText(vi.connectionsPage.configured);
    expect(badges.length).toBe(1);
    expect(screen.getByText(vi.connectionsPage.notConfigured)).toBeInTheDocument();
  });

  it("shows the ignored badge for ignored Telegram channels", () => {
    const connections: ConnectionsInfo = {
      providers: [],
      routes: [],
      vision_routes: [],
      keys: [],
      search_backends: ["duckduckgo"],
      firecrawl_base_url: "",
      telegram: [
        { agent_id: "coach", token_env: "COACH_TOKEN", configured: true, ignored: true },
      ],
    };
    render(<ConnectionsPanel connections={connections} />);

    expect(screen.getByText(vi.connectionsPage.ignored)).toBeInTheDocument();
  });

  it("lists search backends in priority order and says firecrawl is off", () => {
    const connections: ConnectionsInfo = {
      providers: [],
      routes: [],
      vision_routes: [],
      keys: [],
      search_backends: ["duckduckgo"],
      firecrawl_base_url: "",
      telegram: [],
    };
    render(<ConnectionsPanel connections={connections} />);

    expect(screen.getByTestId("search-backends").textContent).toContain("duckduckgo");
    expect(screen.getByText(vi.connectionsPage.firecrawlOff)).toBeInTheDocument();
  });

  it("names the firecrawl host when one is configured", () => {
    const connections: ConnectionsInfo = {
      providers: [],
      routes: [],
      vision_routes: [],
      keys: [],
      search_backends: ["firecrawl", "duckduckgo"],
      firecrawl_base_url: "http://127.0.0.1:3002",
      telegram: [],
    };
    render(<ConnectionsPanel connections={connections} />);

    const list = screen.getByTestId("search-backends");
    expect(list.textContent).toContain("firecrawl");
    expect(
      screen.getByText(vi.connectionsPage.firecrawlAt("http://127.0.0.1:3002")),
    ).toBeInTheDocument();
  });

  it("shows the hint text for the keys section", () => {
    const connections: ConnectionsInfo = {
      providers: [],
      routes: [],
      vision_routes: [],
      keys: [],
      search_backends: ["duckduckgo"],
      firecrawl_base_url: "",
      telegram: [],
    };
    render(<ConnectionsPanel connections={connections} />);

    expect(screen.getByText(vi.connectionsPage.keysHint)).toBeInTheDocument();
  });

  it("shows the page hint at the top", () => {
    const connections: ConnectionsInfo = {
      providers: [],
      routes: [],
      vision_routes: [],
      keys: [],
      search_backends: ["duckduckgo"],
      firecrawl_base_url: "",
      telegram: [],
    };
    render(<ConnectionsPanel connections={connections} />);

    expect(screen.getByText(vi.connectionsPage.hint)).toBeInTheDocument();
  });

  it("renders all sections with correct data testids", () => {
    const connections: ConnectionsInfo = {
      providers: [{ name: "test", built: true }],
      routes: [{ provider: "test", model: "model" }],
      vision_routes: [{ provider: "test", model: "vision" }],
      keys: [{ name: "KEY", present: true }],
      search_backends: ["duckduckgo"],
      firecrawl_base_url: "",
      telegram: [],
    };
    render(<ConnectionsPanel connections={connections} />);

    expect(screen.getByTestId("providers")).toBeInTheDocument();
    expect(screen.getByTestId("routes")).toBeInTheDocument();
    expect(screen.getByTestId("vision-routes")).toBeInTheDocument();
    expect(screen.getByTestId("keys")).toBeInTheDocument();
    expect(screen.queryByTestId("telegram-list")).not.toBeInTheDocument(); // No channels
  });

  it("PRIVACY: shows correct badge for present key", () => {
    const connections: ConnectionsInfo = {
      providers: [],
      routes: [],
      vision_routes: [],
      keys: [
        { name: "TEST_KEY", present: true },
      ],
      search_backends: ["duckduckgo"],
      firecrawl_base_url: "",
      telegram: [],
    };
    render(<ConnectionsPanel connections={connections} />);

    const keysList = screen.getByTestId("keys");
    const badges = keysList.querySelectorAll(".badge");
    expect(badges.length).toBeGreaterThan(0);
    const presentBadge = Array.from(badges).find((b) =>
      b.textContent?.includes(vi.connectionsPage.present),
    );
    expect(presentBadge).toHaveClass("ok");
  });

  it("PRIVACY: does not show empty/missing badge with ok class", () => {
    const connections: ConnectionsInfo = {
      providers: [],
      routes: [],
      vision_routes: [],
      keys: [
        { name: "MISSING_KEY", present: false },
      ],
      search_backends: ["duckduckgo"],
      firecrawl_base_url: "",
      telegram: [],
    };
    render(<ConnectionsPanel connections={connections} />);

    const keysList = screen.getByTestId("keys");
    const badges = keysList.querySelectorAll(".badge.ok");
    const hasAbsentBadge = Array.from(badges).some((b) =>
      b.textContent?.includes(vi.connectionsPage.absent),
    );
    expect(hasAbsentBadge).toBe(false);
  });
});
