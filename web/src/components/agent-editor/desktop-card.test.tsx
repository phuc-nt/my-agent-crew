// An agent's desktop on its page: its mode, its applications and the machine as it stands for
// it, and one picture a person may try. The try is offered only to an agent that is on, waits
// while it runs and gives up after the helper's own limits; a refusal is the server's sentence,
// shown as it is.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentInfo, ComputerMode, DesktopConnection } from "../../api/types";
import { DESKTOP_SHOT_WAIT_MS } from "../../hooks/use-agent-desktop";
import { vi } from "../../i18n/vi";
import { FakeBackend, coachAgent, fakeAgent } from "../../test/fake-backend";
import { DESKTOP_SAID, desktopAbsent, desktopReady } from "../../test/fake-desktop";
import { DesktopCard } from "./desktop-card";

const t = vi.desktop.card;
const READ = "/agents/coach/desktop";
const SHOOT = `${READ}/screenshot`;
let backend: FakeBackend;

afterEach(() => {
  vitest.useRealTimers();
  vitest.restoreAllMocks();
  vitest.unstubAllGlobals();
});

/** A crew whose coach's file says `mode` and `apps`, on a machine that says `machine`. */
function crew(mode: ComputerMode, machine: DesktopConnection, coach: Partial<AgentInfo> = {}) {
  backend = new FakeBackend();
  backend.agents = [fakeAgent, { ...coachAgent, computer: mode, computer_apps: ["Notes"], ...coach }];
  backend.desktop.machine = machine;
  vitest.stubGlobal("fetch", backend.fetch);
  return backend;
}

/** The card as the coach's page draws it, from what its file says. */
function show() {
  const coach = backend.agents.find((a) => a.id === "coach");
  return render(<DesktopCard agentId="coach" savedMode={coach?.computer} savedApps={coach?.computer_apps} />);
}

const settle = () => act(() => new Promise<void>((resolve) => setTimeout(resolve, 0)));
const card = () => within(screen.getByTestId("desktop-card"));
const lines = () => within(screen.getByTestId("desktop-machine-lines")).getAllByRole("listitem").map((li) => li.textContent);
const tryButton = () => screen.queryByTestId("desktop-try") as HTMLButtonElement | null;
const sent = (path: string, method: string) => backend.requests.filter((r) => r.path === path && r.method === method).length;
/** The card once its first read is drawn. */
async function drawn() {
  show();
  await waitFor(() => expect(screen.getByTestId("desktop-mode")).toBeInTheDocument());
}

describe("the card of an agent", () => {
  it("that is off says so and offers no picture", async () => {
    crew("off", desktopReady());
    await drawn();

    expect(card().getByTestId("desktop-mode")).toHaveTextContent(t.mode.off);
    expect(card().queryByTestId("desktop-apps-line")).not.toBeInTheDocument();
    expect(lines()).toEqual([t.ready]);
    expect(tryButton()).not.toBeInTheDocument();
    expect(card().queryByRole("button")).not.toBeInTheDocument();
  });

  it("that is on with no helper on the machine says the helper is the owner's, and nothing else", async () => {
    crew("on", desktopAbsent());
    await drawn();

    expect(card().getByTestId("desktop-mode")).toHaveTextContent(t.mode.on);
    expect(card().getByTestId("desktop-apps-line")).toHaveTextContent(t.apps("Notes"));
    expect(lines()).toEqual([t.noHelper]);
    expect(t.noHelper).toContain("chủ máy");
    expect(tryButton()).toBeEnabled();
  });

  it("that is on with the screen locked says so", async () => {
    crew("on", desktopReady({ locked: true }));
    await drawn();

    expect(lines()).toEqual([t.locked]);
  });

  it("that is ready says so in one line", async () => {
    crew("on", desktopReady(), { computer_apps: ["Notes", "com.apple.Safari"] });
    await drawn();

    expect(lines()).toEqual([t.ready]);
    expect(card().getByTestId("desktop-apps-line")).toHaveTextContent(t.apps("Notes, com.apple.Safari"));
  });

  it("names each thing in the way, a permission missing apart from one not told", async () => {
    crew("on", desktopReady({ display_asleep: true, screen_recording: false, accessibility: null }));
    await drawn();

    expect(lines()).toEqual([
      t.asleep,
      t.missing(vi.desktop.permission.screen_recording),
      t.unknown(vi.desktop.permission.accessibility),
    ]);
    // The lines are said aloud when a read changes them.
    expect(screen.getByTestId("desktop-machine-lines")).toHaveAttribute("role", "status");
  });

  it("with no application says it only looks", async () => {
    crew("on", desktopReady(), { computer_apps: [] });
    await drawn();

    expect(card().getByTestId("desktop-apps-line")).toHaveTextContent(t.lookOnly);
  });

  it("of a server older than the desktop is not drawn, and nothing is asked", async () => {
    crew("on", desktopReady());
    // The coach as that server reports it: without the key.
    render(<DesktopCard agentId="coach" savedMode={undefined} savedApps={undefined} />);
    await settle();

    expect(screen.queryByTestId("desktop-card")).not.toBeInTheDocument();
    expect(sent(READ, "GET")).toBe(0);
  });

  it("whose route the server does not have is not drawn", async () => {
    crew("on", desktopReady());
    backend.desktop.old = true;
    show();

    await waitFor(() => expect(sent(READ, "GET")).toBe(1));
    await settle();
    expect(screen.queryByTestId("desktop-card")).not.toBeInTheDocument();
  });

  it("says why the state could not be read", async () => {
    crew("on", desktopReady());
    vitest.stubGlobal("fetch", async () => new Response(JSON.stringify({ detail: "helper exploded" }), { status: 500 }));
    show();

    await waitFor(() => expect(card().getByTestId("desktop-read-error")).toHaveTextContent(t.readFailed(vi.requestErrors.server(500))));
  });
});

describe("a picture tried from the card", () => {
  it("is shown as the files route serves it, and the machine is read again", async () => {
    crew("on", desktopReady());
    await drawn();
    expect(sent(READ, "GET")).toBe(1);

    await userEvent.click(tryButton() as HTMLButtonElement);

    const shot = await screen.findByTestId("desktop-shot");
    const path = "desktop/0000000000000001-1456x910-1.png";
    expect(shot).toHaveAttribute("href", `/api/agents/coach/files?path=${encodeURIComponent(path)}`);
    expect(within(shot).getByRole("img")).toHaveAttribute("src", `/api/agents/coach/files?path=${encodeURIComponent(path)}`);
    expect(within(shot).getByRole("img")).toHaveAttribute("alt", t.shotAlt(1456, 910));
    expect(sent(SHOOT, "POST")).toBe(1);
    await waitFor(() => expect(sent(READ, "GET")).toBe(2));
  });

  it("is saved under the agent's first write path, and the card follows the path it is told", async () => {
    // A write path is a folder of the workspace, and the server names the picture from there.
    crew("on", desktopReady(), { write_paths: ["records/kept"] });
    await drawn();

    await userEvent.click(tryButton() as HTMLButtonElement);

    const shot = await screen.findByTestId("desktop-shot");
    expect(shot.getAttribute("href")).toBe(
      `/api/agents/coach/files?path=${encodeURIComponent("records/kept/desktop/0000000000000001-1456x910-1.png")}`,
    );
  });

  it.each([
    ["no helper", desktopAbsent(), DESKTOP_SAID.absent],
    ["a locked screen", desktopReady({ locked: true }), DESKTOP_SAID.locked],
    ["no screen recording", desktopReady({ screen_recording: false }), DESKTOP_SAID.noScreen],
  ])("refused for %s shows the server's sentence as it is", async (_why, machine, said) => {
    crew("on", machine);
    await drawn();

    await userEvent.click(tryButton() as HTMLButtonElement);

    await waitFor(() => expect(card().getByTestId("desktop-refused")).toHaveTextContent(said));
    expect(card().getByTestId("desktop-refused").textContent).toBe(said);
    expect(screen.queryByTestId("desktop-shot")).not.toBeInTheDocument();
    expect(tryButton()).toBeEnabled();
  });

  it("refused for an application in front outside the list shows that sentence too", async () => {
    crew("on", desktopReady());
    backend.desktop.refuse.shot = { status: 409, detail: DESKTOP_SAID.outside };
    await drawn();

    await userEvent.click(tryButton() as HTMLButtonElement);

    await waitFor(() => expect(card().getByTestId("desktop-refused").textContent).toBe(DESKTOP_SAID.outside));
  });

  it("that fails otherwise says the request failed, in the page's own words for it", async () => {
    crew("on", desktopReady());
    backend.desktop.refuse.shot = { status: 502, detail: "bad gateway" };
    await drawn();

    await userEvent.click(tryButton() as HTMLButtonElement);

    await waitFor(() =>
      expect(card().getByTestId("desktop-refused")).toHaveTextContent(vi.connectionsPage.failed(vi.requestErrors.server(502))),
    );
  });

  it("holds the button while it runs, and takes one picture for one press", async () => {
    crew("on", desktopReady());
    let release = () => {};
    backend.desktop.holdShot = new Promise<void>((resolve) => {
      release = resolve;
    });
    await drawn();

    await userEvent.click(tryButton() as HTMLButtonElement);

    await waitFor(() => expect(tryButton()).toBeDisabled());
    expect(tryButton()).toHaveTextContent(t.shooting);
    await userEvent.click(tryButton() as HTMLButtonElement);
    expect(sent(SHOOT, "POST")).toBe(1);

    backend.desktop.holdShot = null;
    await act(async () => release());
    await screen.findByTestId("desktop-shot");
    expect(tryButton()).toBeEnabled();
    expect(tryButton()).toHaveTextContent(t.tryShot);
  });

  it("clears the last picture and the last refusal when tried again", async () => {
    crew("on", desktopReady());
    await drawn();
    await userEvent.click(tryButton() as HTMLButtonElement);
    await screen.findByTestId("desktop-shot");

    backend.desktop.refuse.shot = { status: 409, detail: DESKTOP_SAID.outside };
    await userEvent.click(tryButton() as HTMLButtonElement);

    await waitFor(() => expect(card().getByTestId("desktop-refused")).toBeInTheDocument());
    expect(screen.queryByTestId("desktop-shot")).not.toBeInTheDocument();
  });

  it("is given up on after the helper's limits, and an answer that comes later is not drawn", async () => {
    crew("on", desktopReady());
    let release = () => {};
    backend.desktop.holdShot = new Promise<void>((resolve) => {
      release = resolve;
    });
    await drawn();
    vitest.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });

    fireEvent.click(tryButton() as HTMLButtonElement);
    await act(async () => {
      await vitest.advanceTimersByTimeAsync(DESKTOP_SHOT_WAIT_MS - 1);
    });
    expect(tryButton()).toBeDisabled();
    expect(card().queryByTestId("desktop-refused")).not.toBeInTheDocument();

    await act(async () => {
      await vitest.advanceTimersByTimeAsync(1);
    });
    expect(card().getByTestId("desktop-refused")).toHaveTextContent(t.gaveUp);
    expect(tryButton()).toBeEnabled();

    await act(async () => release());
    await act(async () => {
      await vitest.advanceTimersByTimeAsync(0);
    });
    expect(screen.queryByTestId("desktop-shot")).not.toBeInTheDocument();
    expect(card().getByTestId("desktop-refused")).toHaveTextContent(t.gaveUp);
    expect(DESKTOP_SHOT_WAIT_MS).toBeGreaterThan(30_000);
  });

  it("is stopped when the card goes away while it runs", async () => {
    crew("on", desktopReady());
    backend.desktop.holdShot = new Promise<void>(() => undefined);
    let signal: AbortSignal | null | undefined;
    const real = backend.fetch;
    vitest.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith(SHOOT)) signal = init?.signal;
      return real(input, init);
    });
    const view = show();
    await waitFor(() => expect(screen.getByTestId("desktop-mode")).toBeInTheDocument());

    await userEvent.click(tryButton() as HTMLButtonElement);
    await waitFor(() => expect(signal).toBeInstanceOf(AbortSignal));
    expect(signal?.aborted).toBe(false);

    view.unmount();
    expect(signal?.aborted).toBe(true);
  });
});

describe("the machine read again", () => {
  /** What a save of the coach's file leaves on the server, and the card as the page then draws it. */
  function saved(view: ReturnType<typeof render>, coach: Partial<AgentInfo>) {
    backend.agents = backend.agents.map((a) => (a.id === "coach" ? { ...a, ...coach } : a));
    const now = backend.agents.find((a) => a.id === "coach") as AgentInfo;
    view.rerender(<DesktopCard agentId="coach" savedMode={now.computer} savedApps={now.computer_apps} />);
  }

  it("follows a save of the mode, then of the applications, and not a list with the same lines", async () => {
    crew("off", desktopReady());
    const view = show();
    await waitFor(() => expect(card().getByTestId("desktop-mode")).toHaveTextContent(t.mode.off));

    saved(view, { computer: "on" });
    await waitFor(() => expect(card().getByTestId("desktop-mode")).toHaveTextContent(t.mode.on));
    expect(sent(READ, "GET")).toBe(2);

    saved(view, { computer_apps: ["Notes", "com.apple.Safari"] });
    await waitFor(() => expect(card().getByTestId("desktop-apps-line")).toHaveTextContent(t.apps("Notes, com.apple.Safari")));
    expect(sent(READ, "GET")).toBe(3);

    saved(view, { computer_apps: ["Notes", "com.apple.Safari"] });
    await settle();
    expect(sent(READ, "GET")).toBe(3);
  });

  it("keeps the newer answer when an older one arrives after it", async () => {
    crew("off", desktopReady());
    const real = backend.fetch;
    let releaseFirst = () => {};
    let first = true;
    vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      // The answer is what the server says as the request reaches it; only its way back waits.
      const answer = await real(input, init);
      if (first && String(input).endsWith(READ)) {
        first = false;
        await new Promise<void>((resolve) => {
          releaseFirst = resolve;
        });
      }
      return answer;
    });
    const view = show();
    await waitFor(() => expect(sent(READ, "GET")).toBe(1));

    saved(view, { computer: "on" });
    await waitFor(() => expect(card().getByTestId("desktop-mode")).toHaveTextContent(t.mode.on));

    await act(async () => releaseFirst());
    await settle();
    expect(card().getByTestId("desktop-mode")).toHaveTextContent(t.mode.on);
    expect(tryButton()).toBeEnabled();
  });
});
