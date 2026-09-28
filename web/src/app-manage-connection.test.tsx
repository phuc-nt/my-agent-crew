import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, FakeEventSource } from "./test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  FakeEventSource.instances = [];
  vitest.stubGlobal("fetch", backend.fetch);
  vitest.stubGlobal("EventSource", FakeEventSource);
  window.location.hash = "";
});

afterEach(() => {
  vitest.unstubAllGlobals();
  vitest.restoreAllMocks();
});

function stream(): FakeEventSource {
  const source = FakeEventSource.instances.at(-1);
  if (!source) throw new Error("the app has not subscribed to the activity stream");
  return source;
}

function connect() {
  act(() => {
    stream().open();
    stream().emit({ type: "snapshot", runs: [] });
  });
}

async function openManage() {
  render(<App />);
  await screen.findByText(vi.welcomeTitleFor("Agent"));
  await userEvent.click(screen.getByRole("button", { name: /Quản lý/ }));
  return screen.getByRole("main", { name: vi.manage.label });
}

const reads = (path: string) => backend.requests.filter((r) => r.method === "GET" && r.path === path).length;

describe("the manage screen and the live stream", () => {
  it("says the pages stopped following the server when the stream drops, and a retry opens a fresh one", async () => {
    const main = await openManage();
    connect();
    expect(main).not.toHaveTextContent(vi.manage.disconnected);

    const first = stream();
    act(() => first.onerror?.());
    expect(main).toHaveTextContent(vi.manage.disconnected);
    await userEvent.click(within(main).getByRole("button", { name: vi.streamRetryLabel }));

    expect(first.closed).toBe(true);
    expect(stream()).not.toBe(first);
    // Opening again is not a drop, so the notice steps aside while the stream connects.
    expect(main).not.toHaveTextContent(vi.manage.disconnected);
    connect();
    expect(main).not.toHaveTextContent(vi.manage.disconnected);
  });

  it("says nothing while the stream first connects", async () => {
    const main = await openManage();
    expect(within(main).getByRole("status")).toBeEmptyDOMElement();
  });

  it("says the device is offline instead of offering a retry that cannot work", async () => {
    const onLine = vitest.spyOn(window.navigator, "onLine", "get").mockReturnValue(false);
    const main = await openManage();
    act(() => stream().onerror?.());
    expect(main).toHaveTextContent(vi.manage.offline);
    expect(within(main).queryByRole("button", { name: vi.streamRetryLabel })).toBeNull();

    onLine.mockReturnValue(true);
    act(() => {
      window.dispatchEvent(new Event("online"));
    });
    expect(main).toHaveTextContent(vi.manage.disconnected);
    expect(within(main).getByRole("button", { name: vi.streamRetryLabel })).toBeInTheDocument();
  });

  // The stream carries runs only; a server restarted during the drop may have moved a
  // schedule or changed a profile, and nothing else would say so.
  it("reads the crew, the schedules and the totals again when the stream comes back, not when it first opens", async () => {
    await openManage();
    connect();
    await waitFor(() => expect(reads("/stats")).toBeGreaterThan(0));
    const before = { agents: reads("/agents"), jobs: reads("/jobs"), stats: reads("/stats") };

    act(() => stream().onerror?.());
    act(() => stream().open());
    await waitFor(() => expect(reads("/jobs")).toBe(before.jobs + 1));
    expect(reads("/agents")).toBe(before.agents + 1);
    expect(reads("/stats")).toBe(before.stats + 1);
  });
});
