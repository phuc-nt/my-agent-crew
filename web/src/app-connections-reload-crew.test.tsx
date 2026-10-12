// A save on the connections page is applied to the crew that is running: the server builds
// it again. A key may hand an agent a tool it did not hold, and the routes every agent
// falls back on are the routes of each agent that names none. The page reads the crew
// again, so that an editor opened after the save works from the agent as it is now.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentInfo, CredentialsInfo } from "./api/types";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, FakeEventSource, fakeAgent } from "./test/fake-backend";
import { radio, rows, ticked } from "./test/tool-picker-screen";

const t = vi.editor;
const words = vi.connectionsPage;
const KEY = "OPENROUTER_API_KEY";
const coach: AgentInfo = { ...fakeAgent, id: "coach", name: "HLV", is_master: false };
/** The crew as the server builds it without the key, and with it: the key builds the
 * provider pictures are sent to, and so the tool that reads them, which a list has a say over. */
const BLIND = [fakeAgent, coach];
const SEEING = BLIND.map((agent) => ({ ...agent, tools: ["image_read", "write_file"], listable_tools: ["image_read", "write_file"] }));

let backend: FakeBackend;
let keySet: boolean;

const keys = (): CredentialsInfo => ({
  file: "/h/env",
  items: [{ name: KEY, group: "model", secret: true, url: false, present: keySet, source: keySet ? "file" : null, checkable: false, editable: true }],
  restart_required: null,
});

/** The fake server with the routes of a key in front of it. A key set or removed, and the
 * routes saved, are applied to the crew before the answer leaves, as the server does. */
const served = async (input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> => {
  const { pathname } = new URL(String(input), "http://fake");
  if (pathname === "/api/connections/routes" && init.method === "PUT") {
    // Neither agent names a route of its own: each runs on the ones just saved.
    const { routes } = JSON.parse(String(init.body));
    backend.agents = backend.agents.map((agent) => ({ ...agent, routes }));
  }
  if (!pathname.startsWith("/api/credentials")) return backend.fetch(input, init);
  if (init.method === "PUT") [keySet, backend.agents] = [true, SEEING];
  if (init.method === "DELETE") [keySet, backend.agents] = [false, BLIND];
  return new Response(JSON.stringify(keys()), { headers: { "content-type": "application/json" } });
};

beforeEach(() => {
  backend = new FakeBackend();
  backend.agents = BLIND;
  keySet = false;
  FakeEventSource.instances = [];
  vitest.stubGlobal("fetch", served);
  vitest.stubGlobal("EventSource", FakeEventSource);
  window.location.hash = "#/manage/connections";
});

afterEach(() => {
  vitest.unstubAllGlobals();
  vitest.restoreAllMocks();
  window.location.hash = "";
});

const keyRow = async () => within(await screen.findByTestId(`credential-${KEY}`));
const crewReads = () => backend.requests.filter((r) => r.method === "GET" && r.path === "/agents").length;
const editor = () => within(screen.getByTestId("agent-editor"));

/** Opens the coach's editor the way a person gets there: the crew page, then its card. */
async function opensCoach() {
  await userEvent.click(within(screen.getByRole("navigation", { name: vi.manage.nav })).getByRole("button", { name: vi.crew.tab }));
  const cards = await screen.findAllByTestId("crew-agent");
  await userEvent.click(within(cards[1]).getByRole("button", { name: vi.crew.edit }));
  await screen.findByTestId("agent-editor");
}

/** Saves the form, and returns the profile of every save the server took. */
async function saved() {
  await userEvent.click(editor().getByRole("button", { name: t.save }));
  await waitFor(() => expect(editor().getByText(t.clean)).toBeInTheDocument());
  return backend.requests.filter((r) => r.method === "PATCH").map((r) => (r.body as { profile: object }).profile);
}

describe("the editor opened after a save on the connections page", () => {
  it("offers the tool a saved key built, and starts the agent's list with it", async () => {
    render(<App />);
    const row = await keyRow();
    expect(crewReads()).toBe(1);

    await userEvent.click(row.getByRole("button", { name: words.set }));
    await userEvent.type(row.getByLabelText(words.valueFor(KEY)), "a-key");
    await userEvent.click(row.getByRole("button", { name: words.save }));
    expect(await row.findByText(words.saved)).toBeInTheDocument();
    // Read once more for the save: the crew the server built from the key.
    expect(crewReads()).toBe(2);

    await opensCoach();
    expect(rows()).toEqual(["image_read", "write_file"]);
    await userEvent.click(radio(t.toolsPick));
    // What the agent holds today: a list that left the new tool out would take it away.
    expect(ticked()).toEqual(["image_read", "write_file"]);
    expect(await saved()).toEqual([{ tools: ["image_read", "write_file"] }]);
  });

  it("has no row for the tool that went with a key that was removed", async () => {
    [keySet, backend.agents] = [true, SEEING];
    vitest.spyOn(window, "confirm").mockReturnValue(true);
    render(<App />);
    const row = await keyRow();

    await userEvent.click(row.getByRole("button", { name: words.remove }));
    expect(await row.findByText(words.removed)).toBeInTheDocument();

    await opensCoach();
    expect(rows()).toEqual(["write_file"]);
    await userEvent.click(radio(t.toolsPick));
    expect(ticked()).toEqual(["write_file"]);
    expect(await saved()).toEqual([{ tools: ["write_file"] }]);
  });

  it("shows the routes just saved for every agent, on an agent that names none of its own", async () => {
    render(<App />);
    const routes = within(await screen.findByTestId("routes"));

    await userEvent.clear(routes.getByLabelText(t.model));
    await userEvent.type(routes.getByLabelText(t.model), "sonnet");
    await userEvent.click(routes.getByRole("button", { name: words.routesSave }));
    expect(await routes.findByText(words.routesSaved)).toBeInTheDocument();
    expect(crewReads()).toBe(2);

    await opensCoach();
    expect(within(screen.getByTestId("section-model")).getByLabelText(t.model)).toHaveValue("sonnet");
    expect(editor().getByText(t.clean)).toBeInTheDocument();
  });
});
