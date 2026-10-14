// The machine's desktop helper on the connections page: whether one answers, its version,
// a locked or sleeping screen, and each of its two macOS permissions. The one thing the card
// sends is the request for macOS to ask for them, on a press and never by itself, after which
// the page is read again; a permission still missing is the owner's to grant.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi as mock } from "vitest";
import { api } from "../api/client";
import type { ConnectionsInfo, CredentialsInfo, DesktopConnection } from "../api/types";
import type { CredentialsController } from "../hooks/use-credentials";
import type { McpController } from "../hooks/use-mcp-servers";
import { vi } from "../i18n/vi";
import { FakeBackend } from "../test/fake-backend";
import { DESKTOP_SAID, desktopAbsent, desktopReady } from "../test/fake-desktop";
import { ConnectionsPanel } from "./connections-panel";

const t = vi.desktop.machine;
const ASK = "/desktop/permissions";

const info: CredentialsInfo = { file: "/h/env", items: [], restart_required: null };
const credentials: CredentialsController = {
  info,
  error: null,
  save: mock.fn(async () => info),
  remove: mock.fn(async () => info),
  check: mock.fn(async () => ({ ok: true, detail: "" })),
};
const nothing = async () => undefined;
const mcp: McpController = { servers: [], error: null, refresh: nothing, keysChanged: nothing, crewChanged: nothing, reconnect: nothing, signIn: nothing, signOut: nothing };

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  mock.stubGlobal("fetch", backend.fetch);
});

afterEach(() => {
  mock.restoreAllMocks();
  mock.unstubAllGlobals();
});

/** The page as the screen holds it: read again whenever something on it says it changed. */
function Page({ first }: { first: ConnectionsInfo }) {
  const [connections, setConnections] = useState(first);
  const rebuilt = async () => setConnections(await api.connections());
  return <ConnectionsPanel connections={connections} credentials={credentials} mcp={mcp} onChanged={rebuilt} />;
}

/** The page on a machine whose helper says `machine`, or on a server that says nothing of a
 *  desktop when it is null. */
async function show(machine: DesktopConnection | null) {
  backend.desktop.old = machine === null;
  if (machine) backend.desktop.machine = machine;
  const first = await api.connections();
  backend.requests = [];
  render(<Page first={first} />);
}

const settle = () => act(() => new Promise<void>((resolve) => setTimeout(resolve, 0)));
const card = () => within(screen.getByTestId("desktop-machine"));
const state = () => screen.getByTestId("desktop-machine-state");
const permission = (name: string) => screen.getByTestId(`desktop-permission-${name}`);
const askButton = () => screen.queryByTestId("desktop-ask") as HTMLButtonElement | null;
const asks = () => backend.requests.filter((r) => r.path === ASK);
const reads = () => backend.requests.filter((r) => r.method === "GET" && r.path === "/connections").length;

describe("the desktop card of the connections page", () => {
  it("is not drawn for a server that says nothing of a desktop", async () => {
    await show(null);

    expect(screen.queryByTestId("desktop-machine")).not.toBeInTheDocument();
    expect(screen.queryByText(vi.desktop.title)).not.toBeInTheDocument();
    expect(screen.getByTestId("connections")).toBeInTheDocument();
  });

  it("says there is no helper, that it is the owner's, and offers nothing to press", async () => {
    await show(desktopAbsent());

    expect(card().getByText(vi.desktop.title)).toBeInTheDocument();
    expect(state()).toHaveTextContent(t.absent);
    expect(t.absent).toContain("chủ máy");
    expect(screen.queryByTestId("desktop-permissions")).not.toBeInTheDocument();
    expect(askButton()).not.toBeInTheDocument();
    expect(card().queryByRole("button")).not.toBeInTheDocument();
  });

  it("says a helper is running, its version, and both permissions granted, with nothing to ask", async () => {
    await show(desktopReady({ version: "0.3.1" }));

    expect(within(state()).getByText(t.present)).toHaveClass("badge", "ok");
    expect(state()).toHaveTextContent(t.version("0.3.1"));
    expect(state()).not.toHaveTextContent(t.locked);
    expect(state()).not.toHaveTextContent(t.asleep);
    for (const name of ["screen_recording", "accessibility"] as const) {
      expect(permission(name)).toHaveTextContent(vi.desktop.permission[name]);
      expect(within(permission(name)).getByText(t.granted)).toHaveClass("badge", "ok");
    }
    expect(askButton()).not.toBeInTheDocument();
  });

  it("says a locked and a sleeping screen", async () => {
    await show(desktopReady({ locked: true, display_asleep: true }));

    expect(within(state()).getByText(t.locked)).toHaveClass("badge", "warn");
    expect(within(state()).getByText(t.asleep)).toHaveClass("badge", "warn");
  });

  it("says a permission missing, and offers to ask for it", async () => {
    await show(desktopReady({ accessibility: false }));

    expect(within(permission("accessibility")).getByText(t.missing)).toHaveClass("badge", "warn");
    expect(within(permission("screen_recording")).getByText(t.granted)).toBeInTheDocument();
    expect(askButton()).toHaveTextContent(t.ask);
    expect(card().getByText(t.askHint)).toBeInTheDocument();
  });

  it("says a permission the helper has not told, apart from one missing, and offers to ask for it", async () => {
    await show(desktopReady({ screen_recording: null }));

    const unknown = within(permission("screen_recording")).getByText(t.unknown);
    expect(unknown).toHaveClass("badge");
    expect(unknown).not.toHaveClass("warn");
    expect(unknown).not.toHaveClass("ok");
    expect(askButton()).toBeInTheDocument();
  });

  it("asks for nothing as it is drawn, nor while it stays on screen", async () => {
    await show(desktopReady({ accessibility: false, screen_recording: null }));
    await settle();
    await settle();

    expect(asks()).toEqual([]);
    expect(backend.desktop.presses).toBe(0);
  });
});

describe("asking for the permissions", () => {
  it("sends one request for one press, then reads the page again and draws what it says", async () => {
    await show(desktopReady({ accessibility: false }));
    backend.desktop.granted = { accessibility: true };

    await userEvent.click(askButton() as HTMLButtonElement);

    await waitFor(() => expect(within(permission("accessibility")).getByText(t.granted)).toBeInTheDocument());
    expect(asks()).toEqual([{ method: "POST", path: ASK, body: null }]);
    expect(backend.desktop.presses).toBe(1);
    expect(reads()).toBe(1);
    // Granted now, so there is nothing left to ask for.
    expect(askButton()).not.toBeInTheDocument();
    expect(screen.queryByTestId("desktop-still-missing")).not.toBeInTheDocument();
  });

  it("is held while the request is out, so a second press sends nothing", async () => {
    await show(desktopReady({ screen_recording: false }));
    let land = () => {};
    mock.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      const answer = await backend.fetch(input, init);
      if (init?.method === "POST") await new Promise<void>((resolve) => (land = resolve));
      return answer;
    });

    await userEvent.click(askButton() as HTMLButtonElement);
    await waitFor(() => expect(askButton()).toBeDisabled());
    expect(askButton()).toHaveTextContent(t.asking);
    await userEvent.click(askButton() as HTMLButtonElement);
    expect(backend.desktop.presses).toBe(1);

    await act(async () => land());
    await waitFor(() => expect(askButton()).toBeEnabled());
    expect(backend.desktop.presses).toBe(1);
  });

  it("says a permission still missing afterwards is the owner's to grant in System Settings", async () => {
    await show(desktopReady({ screen_recording: false }));

    await userEvent.click(askButton() as HTMLButtonElement);

    const still = await screen.findByTestId("desktop-still-missing");
    expect(still).toHaveTextContent(t.stillMissing(vi.desktop.permission.screen_recording));
    expect(still).toHaveTextContent("Cài đặt hệ thống");
    expect(reads()).toBe(1);
  });

  it("shows the server's sentence for a 409 as it is, and still reads the page again", async () => {
    await show(desktopReady({ locked: true, accessibility: false }));

    await userEvent.click(askButton() as HTMLButtonElement);

    const error = await screen.findByTestId("desktop-ask-error");
    expect(error.textContent).toBe(DESKTOP_SAID.locked);
    expect(error).toHaveAttribute("role", "alert");
    expect(screen.queryByTestId("desktop-still-missing")).not.toBeInTheDocument();
    await waitFor(() => expect(reads()).toBe(1));
    expect(askButton()).toBeEnabled();
  });

  it("clears the last refusal when asked again", async () => {
    await show(desktopReady({ accessibility: false }));
    backend.desktop.refuse.ask = { status: 409, detail: DESKTOP_SAID.absent };
    await userEvent.click(askButton() as HTMLButtonElement);
    await screen.findByTestId("desktop-ask-error");

    backend.desktop.refuse = {};
    backend.desktop.granted = { accessibility: true };
    await userEvent.click(screen.getByTestId("desktop-ask"));

    await waitFor(() => expect(screen.queryByTestId("desktop-ask-error")).not.toBeInTheDocument());
    expect(backend.desktop.presses).toBe(2);
  });
});
