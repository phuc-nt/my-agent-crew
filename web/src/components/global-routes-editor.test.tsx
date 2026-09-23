import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi as mock } from "vitest";
import { api } from "../api/client";
import type { ConnectionsInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { GlobalRoutesEditor } from "./global-routes-editor";

const t = vi.connectionsPage;

const connections: ConnectionsInfo = {
  providers: [
    { name: "openrouter", built: true },
    { name: "ollama", built: true },
  ],
  routes: [{ provider: "openrouter", model: "deepseek/v4" }],
  routes_source: "config",
  vision_routes: [],
  keys: [],
  search_backends: ["duckduckgo"],
  firecrawl_base_url: "",
  telegram: [],
};

const models = () =>
  within(screen.getByTestId("global-route-editor"))
    .getAllByLabelText(vi.editor.model)
    .map((field) => (field as HTMLInputElement).value);

afterEach(() => mock.restoreAllMocks());

describe("GlobalRoutesEditor", () => {
  it("saves an added fallback and reloads what the server kept", async () => {
    const setRoutes = mock
      .spyOn(api, "setRoutes")
      .mockResolvedValue({ ...connections, restart_required: null });
    const onSaved = mock.fn();
    render(<GlobalRoutesEditor connections={connections} onSaved={onSaved} />);
    const save = screen.getByRole("button", { name: t.routesSave });
    expect(save).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: vi.editor.addRoute }));
    // A route with no model yet is not sent.
    expect(save).toBeDisabled();
    const [, added] = within(screen.getByTestId("global-route-editor")).getAllByLabelText(vi.editor.model);
    fireEvent.change(added, { target: { value: " qwen3:8b " } });
    fireEvent.click(save);

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(t.routesSaved));
    expect(setRoutes).toHaveBeenCalledWith([
      { provider: "openrouter", model: "deepseek/v4" },
      { provider: "openrouter", model: "qwen3:8b" },
    ]);
    expect(onSaved).toHaveBeenCalled();
  });

  it("says why a list was refused and keeps the draft to fix", async () => {
    mock.spyOn(api, "setRoutes").mockRejectedValue(new Error("chưa có nhà cung cấp ollama"));
    render(<GlobalRoutesEditor connections={connections} onSaved={mock.fn()} />);

    fireEvent.change(screen.getByLabelText(vi.editor.provider), { target: { value: "ollama" } });
    fireEvent.click(screen.getByRole("button", { name: t.routesSave }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("ollama"));
    expect(screen.getByLabelText(vi.editor.provider)).toHaveValue("ollama");
    fireEvent.click(screen.getByRole("button", { name: t.routesReset }));
    expect(screen.getByLabelText(vi.editor.provider)).toHaveValue("openrouter");
  });

  it("shows routes the variable decides without a way to save over them", () => {
    render(
      <GlobalRoutesEditor connections={{ ...connections, routes_source: "env" }} onSaved={mock.fn()} />,
    );

    expect(models()).toEqual(["deepseek/v4"]);
    expect(screen.getByLabelText(vi.editor.model)).toBeDisabled();
    expect(screen.queryByRole("button", { name: t.routesSave })).toBeNull();
    expect(screen.getByTestId("routes-source")).toHaveTextContent("MY_AGENT_ROUTES");
  });

  it("starts an added row on a real provider, not the echo one that sorts first", () => {
    const withFake = {
      ...connections,
      providers: [{ name: "fake", built: true }, ...connections.providers],
    };
    render(<GlobalRoutesEditor connections={withFake} onSaved={mock.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: vi.editor.addRoute }));

    const [, added] = screen.getAllByLabelText(vi.editor.provider);
    expect(added).toHaveValue("openrouter");
  });

  it("takes the list the server kept, so a save that changed nothing leaves nothing to save", async () => {
    // The server drops the duplicate; the page, still showing the old routes, must not
    // keep offering Save for a list that is already what is saved.
    mock.spyOn(api, "setRoutes").mockResolvedValue({ ...connections, restart_required: null });
    render(<GlobalRoutesEditor connections={connections} onSaved={mock.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: vi.editor.addRoute }));
    const [, added] = within(screen.getByTestId("global-route-editor")).getAllByLabelText(vi.editor.model);
    fireEvent.change(added, { target: { value: "deepseek/v4" } });
    fireEvent.click(screen.getByRole("button", { name: t.routesSave }));

    await waitFor(() => expect(models()).toEqual(["deepseek/v4"]));
    expect(screen.getByRole("button", { name: t.routesSave })).toBeDisabled();
  });

  it("starts the draft again when the saved routes change", () => {
    const { rerender } = render(<GlobalRoutesEditor connections={connections} onSaved={mock.fn()} />);
    rerender(
      <GlobalRoutesEditor
        connections={{ ...connections, routes: [{ provider: "ollama", model: "llama" }] }}
        onSaved={mock.fn()}
      />,
    );

    expect(models()).toEqual(["llama"]);
  });
});
