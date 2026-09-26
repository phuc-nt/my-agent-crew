import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { useVersionCheck } from "./use-version-check";

/** What the server answers; null plays a server that is down. */
let server: { version: string | null; entry: string | null };
let calls: string[];
let now: number;

beforeEach(() => {
  server = { version: "0.8.0", entry: "/assets/index-first.js" };
  calls = [];
  now = 1_000_000;
  vitest.spyOn(Date, "now").mockImplementation(() => now);
  vitest.stubGlobal("fetch", async (input: RequestInfo | URL) => {
    const path = String(input);
    calls.push(path);
    if (path === "/api/health" && server.version) return Response.json({ status: "ok", version: server.version });
    if (path === "/" && server.entry) {
      return new Response(`<script type="module" crossorigin src="${server.entry}"></script>`);
    }
    return new Response("down", { status: 502 });
  });
});

afterEach(() => {
  for (const script of document.head.querySelectorAll("script")) script.remove();
  vitest.restoreAllMocks();
  vitest.unstubAllGlobals();
});

/** Makes this page a built one, loaded with `entry`. */
function built(entry = "/assets/index-first.js") {
  const script = document.createElement("script");
  script.setAttribute("type", "module");
  script.setAttribute("src", entry);
  document.head.append(script);
}

async function mount() {
  const hook = renderHook(({ connected }) => useVersionCheck(connected), { initialProps: { connected: true } });
  await waitFor(() => expect(hook.result.current.pageVersion).toBe("0.8.0"));
  return hook;
}

/** Lets every pending fetch and state update land. */
const settle = () => act(() => new Promise((resolve) => setTimeout(resolve, 0)));

function focusLater() {
  now += 31_000;
  act(() => {
    window.dispatchEvent(new Event("focus"));
  });
}

const indexLooks = () => calls.filter((c) => c === "/").length;

describe("useVersionCheck", () => {
  it("offers the new build once the server's page loads another entry", async () => {
    built();
    const { result } = await mount();
    expect(result.current.stale).toBe(false);

    server.entry = "/assets/index-second.js";
    focusLater();
    await waitFor(() => expect(result.current.stale).toBe(true));
  });

  it("stays quiet while the server serves the build on screen", async () => {
    built();
    const { result } = await mount();
    focusLater();
    await settle();
    expect(indexLooks()).toBe(2);
    expect(result.current.stale).toBe(false);
  });

  it("counts a new server version as a new build and reports both", async () => {
    built();
    const { result } = await mount();
    server.version = "0.9.0";
    focusLater();
    await waitFor(() => expect(result.current.stale).toBe(true));
    expect(result.current.pageVersion).toBe("0.8.0");
    expect(result.current.serverVersion).toBe("0.9.0");
  });

  it("says nothing when the server cannot be reached", async () => {
    built();
    const { result } = await mount();
    server = { version: null, entry: null };
    focusLater();
    await settle();
    expect(result.current.stale).toBe(false);
    expect(result.current.serverVersion).toBeNull();
    expect(result.current.pageVersion).toBe("0.8.0");
  });

  it("looks at most every half minute on focus, and always after the stream reconnects", async () => {
    built();
    const { rerender } = await mount();
    expect(indexLooks()).toBe(1);

    act(() => {
      window.dispatchEvent(new Event("focus"));
    });
    expect(indexLooks()).toBe(1);

    rerender({ connected: false });
    rerender({ connected: true });
    expect(indexLooks()).toBe(2);

    now += 31_000;
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(indexLooks()).toBe(3);
    await settle();
  });

  it("is inert on the dev server, which has no hashed entry to compare", async () => {
    const { result, rerender } = await mount();
    server = { version: "0.9.0", entry: "/assets/index-second.js" };
    focusLater();
    rerender({ connected: false });
    rerender({ connected: true });
    act(() => result.current.check());
    await settle();
    expect(indexLooks()).toBe(0);
    expect(result.current.stale).toBe(false);
    // Settings still names the versions it saw.
    expect(result.current.serverVersion).toBe("0.9.0");
  });
});
