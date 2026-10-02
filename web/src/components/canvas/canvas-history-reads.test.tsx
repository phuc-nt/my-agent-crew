import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import { RETRY_DELAYS_MS } from "../../lib/canvas-types";
import { landed, startServer, stopServer, wait } from "../../test/canvas-hook";
import {
  diff,
  history,
  historyShown,
  openHistory,
  pick,
  restoreButton,
  rows,
  threeVersions,
  writes,
} from "../../test/canvas-history";
import { editor, openPanel, typeInto } from "../../test/canvas-panel";
import type { FakeBackend } from "../../test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
  vitest.setSystemTime(new Date("2026-10-02T03:05:00Z"));
  threeVersions(backend);
});

afterEach(stopServer);

const alert = () => within(history()).queryByRole("alert")?.textContent ?? null;

describe("what the history reads", () => {
  it("reads the list again when a newer version is announced while it is open", async () => {
    await openPanel();
    await openHistory();

    act(() => {
      backend.canvas.write("a1", "một\nhai\nbốn\nnăm", { author: "agent:ming" });
    });
    await landed();

    expect(rows()[0]).toMatch(/^v5 · Ming · /);
  });

  it("reads a version again when it is picked again after its read failed, and stops saying so", async () => {
    await openPanel();
    await openHistory();
    backend.canvas.refuseNext("GET /artifacts/a1/versions/1", 503);

    await pick(1);
    expect(alert()).toBe(vi.canvas.versionFailed);
    expect(diff()).toBeNull();

    await pick(1);

    expect(alert()).toBeNull();
    expect(diff()).toBe("+ một");
  });

  it("takes the list refused for a canvas deleted meanwhile for the deletion", async () => {
    await openPanel();
    backend.canvas.onEvent = null;
    backend.canvas.remove("a1");

    await openHistory();

    expect(historyShown()).toBe(false);
    expect(screen.getByRole("alert").textContent).toBe(`${vi.canvas.gone} ${vi.canvas.goneHint}`);
  });

  it("takes a version refused for a canvas deleted meanwhile for the deletion", async () => {
    await openPanel();
    await openHistory();
    backend.canvas.onEvent = null;
    backend.canvas.remove("a1");

    await pick(1);

    expect(historyShown()).toBe(false);
    expect(screen.getByRole("alert").textContent).toBe(`${vi.canvas.gone} ${vi.canvas.goneHint}`);
  });
});

describe("a restore on its way or refused", () => {
  it("cannot be asked for again while it is on its way", async () => {
    await openPanel();
    await openHistory();
    await pick(1);
    const release = backend.canvas.holdNext("POST");

    fireEvent.click(restoreButton());
    await landed();
    expect(restoreButton()).toBeDisabled();

    await act(release);
    await landed();
    expect(historyShown()).toBe(false);
    expect(editor()?.value).toBe("một");
  });

  it("can be asked for again once the server refused it", async () => {
    await openPanel();
    await openHistory();
    await pick(1);
    backend.canvas.refuseNext("POST", 503);

    fireEvent.click(restoreButton());
    await landed();

    expect(alert()).toBe(vi.canvas.restoreFailed(vi.canvas.reasons.server));
    expect(restoreButton()).toBeEnabled();
  });

  it("says no more that the typing held it back once a retry saves the typing", async () => {
    await openPanel();
    typeInto("một\nhai\nbốn\nnăm");
    await openHistory();
    await pick(1);
    backend.canvas.refuseNext("PUT", 503);

    fireEvent.click(restoreButton());
    await landed();
    expect(alert()).toBe(vi.canvas.restoreFailed(vi.canvas.reasons.server));

    wait(RETRY_DELAYS_MS[0]);
    await landed();

    expect(writes(backend).map((write) => write.method)).toEqual(["PUT", "PUT"]);
    expect(alert()).toBeNull();
  });
});
