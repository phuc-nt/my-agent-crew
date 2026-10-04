import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import { landed, startServer, stopServer } from "../../test/canvas-hook";
import { diff, history, openHistory, pick, writes } from "../../test/canvas-history";
import { openPanel } from "../../test/canvas-panel";
import type { FakeBackend } from "../../test/fake-backend";
import { SAMPLES } from "../../test/fake-canvas-kinds";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
  vitest.setSystemTime(new Date("2026-10-02T03:05:00Z"));
});

afterEach(stopServer);

const versionsRead = () =>
  backend.requests.filter((request) => request.path.startsWith("/artifacts/a1/versions/")).map((request) => request.path);
const historyPicture = () => history().querySelector("img.canvas-picture");

describe("the history of a canvas with long lines", () => {
  it("cuts a line past the most a diff shows, and says how many characters it left out", async () => {
    backend.canvas.add({ title: "Trang một dòng", kind: "html", content: "<p>ngắn</p>" });
    backend.canvas.write("a1", "x".repeat(5000), { author: "agent:ming" });
    await openPanel();

    await openHistory();

    const added = history().querySelector(".canvas-diff .added");
    expect(added?.textContent).toBe(`+ ${"x".repeat(2000)}${vi.canvas.cutChars(3000)}`);
    expect(added?.querySelector(".cut")?.textContent).toBe(vi.canvas.cutChars(3000));
    expect(history().querySelector(".canvas-diff .removed")?.textContent).toBe("- <p>ngắn</p>");
    expect(history().querySelector(".canvas-diff .removed .cut")).toBeNull();
  });
});

describe("the history of an image", () => {
  it("shows each version as its own picture, with no lines to compare and nothing to tick", async () => {
    backend.canvas.add({ ...SAMPLES.image, agent_id: "ming" });
    backend.canvas.write("a1", null, { author: "agent:ming" });
    await openPanel();

    await openHistory();

    expect(versionsRead()).toEqual(["/artifacts/a1/versions/2", "/artifacts/a1/versions/1"]);
    expect(historyPicture()?.getAttribute("src")).toBe("/api/artifacts/a1/raw?version=2");
    expect(historyPicture()?.getAttribute("alt")).toBe(vi.canvas.versionImage(2));
    expect(diff()).toBeNull();
    expect(within(history()).queryByRole("checkbox")).toBeNull();
    expect(within(history()).queryByRole("button", { name: vi.canvas.restore })).toBeNull();

    await pick(1);

    expect(historyPicture()?.getAttribute("src")).toBe("/api/artifacts/a1/raw?version=1");
    expect(historyPicture()?.getAttribute("alt")).toBe(vi.canvas.versionImage(1));
    expect(within(history()).getByText(vi.canvas.firstVersion)).toBeTruthy();
    expect(diff()).toBeNull();
  });

  it("restores an older picture with the restore alone, and shows it as the newest", async () => {
    backend.canvas.add({ ...SAMPLES.image, agent_id: "ming" });
    backend.canvas.write("a1", null, { author: "agent:ming" });
    await openPanel();
    await openHistory();
    await pick(1);

    const restore = within(history()).getByRole("button", { name: vi.canvas.restore }) as HTMLButtonElement;
    expect(restore.disabled).toBe(false);
    fireEvent.click(restore);
    await landed();

    expect(writes(backend)).toEqual([{ method: "POST", path: "/artifacts/a1/restore", body: { version: 1 } }]);
    expect(screen.queryByRole("region", { name: vi.canvas.historyTitle })).toBeNull();
    expect(document.querySelector("img.canvas-picture")?.getAttribute("src")).toBe("/api/artifacts/a1/raw?version=3");
    expect(backend.canvas.content("a1")).toBeNull();
  });
});
