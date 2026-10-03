import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { vi } from "../../i18n/vi";
import { landed, startServer, stopServer, wait } from "../../test/canvas-hook";
import { history, openHistory, pick, threeVersions } from "../../test/canvas-history";
import { openPanel, saveState, typeInto } from "../../test/canvas-panel";
import type { FakeBackend } from "../../test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
});

afterEach(stopServer);

const MB = 1024 * 1024;

/** The server refuses the next save for being over a limit that no kind of canvas has. */
const refuseOverThreeMegabytes = () => backend.canvas.refuseNext("PUT", 413, { size: 3 * MB + 1, cap: 3 * MB });

describe("the size a save was held to, said where the panel says why it did not land", () => {
  it("is beside the version line and in the notice of a canvas asked to close", async () => {
    backend.canvas.add({ content: "a" });
    refuseOverThreeMegabytes();
    await openPanel({ stuck: true });

    typeInto("ab");
    wait(1500);
    await landed();

    expect(saveState()).toBe("Không lưu được: canvas vượt quá 3 MB");
    expect(screen.getByRole("alert").textContent).toContain("Chưa lưu được: canvas vượt quá 3 MB.");
  });

  it("is in the history when a restore waits on typing that cannot be saved", async () => {
    threeVersions(backend);
    await openPanel();
    typeInto("một\nhai\nbốn\nnăm");
    await openHistory();
    await pick(1);
    refuseOverThreeMegabytes();

    fireEvent.click(within(history()).getByRole("button", { name: vi.canvas.restore }));
    await landed();

    expect(within(history()).getByRole("alert").textContent).toBe("Không khôi phục được: canvas vượt quá 3 MB");
  });
});
