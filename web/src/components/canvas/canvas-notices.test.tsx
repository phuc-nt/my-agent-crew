import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { vi } from "../../i18n/vi";
import { DRAFT_DELAY_MS } from "../../lib/canvas-runner";
import { landed, startServer, stopServer, wait } from "../../test/canvas-hook";
import { editor, openPanel, typeInto } from "../../test/canvas-panel";
import type { FakeBackend } from "../../test/fake-backend";
import { refusingStorage } from "../../test/memory-storage";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
});

afterEach(stopServer);

describe("the notices over a canvas", () => {
  it("says the canvas could not be opened, and opens it on retry", async () => {
    backend.canvas.add({ title: "Ghi chú", content: "Bước một\n" });
    backend.canvas.refuseNext("GET /artifacts/a1", 503);
    await openPanel();
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(vi.canvas.loadFailed);

    fireEvent.click(within(alert).getByRole("button", { name: vi.canvas.retry }));
    await landed();

    expect(editor()?.value).toBe("Bước một\n");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says when this device cannot keep the typing as a draft", async () => {
    backend.canvas.add({ title: "Ghi chú", content: "a" });
    refusingStorage();
    await openPanel();

    typeInto("ab");
    wait(DRAFT_DELAY_MS);
    await landed();

    expect(screen.getByText(vi.canvas.draftFailed)).toBeTruthy();
  });
});
