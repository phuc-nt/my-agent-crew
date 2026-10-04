import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import { landed, startServer, stopServer, wait } from "../../test/canvas-hook";
import { diff, history, openHistory, pick, picked, rows, threeVersions, writes } from "../../test/canvas-history";
import { editor, openPanel, typeInto, versionLine } from "../../test/canvas-panel";
import type { FakeBackend } from "../../test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
  vitest.setSystemTime(new Date("2026-10-02T03:05:00Z"));
});

afterEach(stopServer);

const versionsRead = () =>
  backend.requests.filter((request) => request.path.startsWith("/artifacts/a1/versions/")).map((request) => request.path);

describe("the versions of a canvas", () => {
  it("lists each version, the newest first, and compares one with the version listed before it", async () => {
    threeVersions(backend);
    await openPanel();

    await openHistory();

    expect(rows()).toEqual(["v4 · bạn · 4 phút · 15 B", "v2 · Ming · 4 phút · 9 B", "v1 · bạn · 5 phút · 5 B"]);
    expect(picked()).toMatch(/^v4 /);
    expect(versionsRead()).toEqual(["/artifacts/a1/versions/4", "/artifacts/a1/versions/2"]);
    expect(diff()).toBe("  một  hai+ bốn");
    expect(within(history()).queryByRole("button", { name: vi.canvas.restore })).toBeNull();

    await pick(2);
    expect(versionsRead()).toEqual(["/artifacts/a1/versions/4", "/artifacts/a1/versions/2", "/artifacts/a1/versions/1"]);
    expect(diff()).toBe("  một+ hai");
  });

  it("compares with the oldest version kept on request, and says the oldest has none before it", async () => {
    threeVersions(backend);
    await openPanel();
    await openHistory();

    fireEvent.click(within(history()).getByRole("checkbox", { name: vi.canvas.compareFirst }));
    await landed();
    expect(diff()).toBe("  một+ hai+ bốn");

    await pick(1);
    expect(within(history()).queryByRole("checkbox")).toBeNull();
    expect(within(history()).getByText(vi.canvas.firstVersion)).toBeTruthy();
    expect(diff()).toBe("+ một");
  });

  it("calls a version read from the canvas's file by that, not by the word the server keeps for it", async () => {
    backend.canvas.add({ content: "a", source: "workspace:ming/a.md" });
    backend.canvas.files.put("workspace:ming/a.md", "từ tệp");
    await backend.canvas.route("/artifacts/a1/reimport", "POST", { base_version: 1 }, new URLSearchParams());
    await openPanel();

    await openHistory();

    expect(rows()).toEqual([`v2 · bạn · 4 phút · 10 B${vi.canvas.importedNote}`, "v1 · bạn · 5 phút · 1 B"]);
    expect(history().textContent).not.toMatch(/import/);
  });

  it("shows a note that only opens with the word the server keeps for a re-import as it is written", async () => {
    backend.canvas.add({ content: "a" });
    backend.canvas.write("a1", "ab", { author: "user" }).note = "imported by hand";
    await openPanel();

    await openHistory();

    expect(rows()[0]).toBe("v2 · bạn · 4 phút · 2 Bimported by hand");
  });

  it("closes without restoring anything", async () => {
    threeVersions(backend);
    await openPanel();
    await openHistory();

    fireEvent.click(within(history()).getByRole("button", { name: vi.canvas.close }));

    expect(screen.queryByRole("region", { name: vi.canvas.historyTitle })).toBeNull();
    expect(editor()?.value).toBe("một\nhai\nbốn");
  });
});

describe("restoring a version", () => {
  it("saves the typing first, then makes the version picked the newest without waiting for the event", async () => {
    threeVersions(backend);
    await openPanel();
    typeInto("một\nhai\nbốn\nnăm");
    await openHistory();
    await pick(1);
    backend.canvas.onEvent = null;

    fireEvent.click(within(history()).getByRole("button", { name: vi.canvas.restore }));
    await landed();

    expect(writes(backend)).toEqual([
      { method: "PUT", path: "/artifacts/a1", body: { content: "một\nhai\nbốn\nnăm", base_version: 4 } },
      { method: "POST", path: "/artifacts/a1/restore", body: { version: 1 } },
    ]);
    expect(screen.queryByRole("region", { name: vi.canvas.historyTitle })).toBeNull();
    expect(editor()?.value).toBe("một");
    expect(versionLine()).toMatch(/^v6 · bạn · /);

    typeInto("một!");
    wait(1500);
    await landed();
    expect(writes(backend).at(-1)?.body).toEqual({ content: "một!", base_version: 6 });
  });

  it("shows the restore's own note on the version it made", async () => {
    threeVersions(backend);
    await openPanel();
    await openHistory();
    await pick(2);
    fireEvent.click(within(history()).getByRole("button", { name: vi.canvas.restore }));
    await landed();

    await openHistory();

    expect(rows()[0]).toBe(`v5 · bạn · 4 phút · 9 B${vi.canvas.restoredFrom(2)}`);
  });

  it("restores nothing while the typing cannot be saved, and says why", async () => {
    threeVersions(backend);
    await openPanel();
    typeInto("một\nhai\nbốn\nnăm");
    await openHistory();
    await pick(1);
    backend.canvas.refuseNext("PUT", 422);

    fireEvent.click(within(history()).getByRole("button", { name: vi.canvas.restore }));
    await landed();

    expect(writes(backend).map((write) => write.method)).toEqual(["PUT"]);
    expect(within(history()).getByRole("alert").textContent).toBe("Không khôi phục được: máy chủ không nhận nội dung này");
  });

  it("shows the largest canvases when the server has no room for the restore", async () => {
    threeVersions(backend);
    await openPanel();
    await openHistory();
    await pick(1);
    backend.canvas.refuseNext("POST", 507);

    fireEvent.click(within(history()).getByRole("button", { name: vi.canvas.restore }));
    await landed();

    const banner = within(history()).getByRole("alert");
    expect(within(banner).getAllByRole("listitem").map((item) => item.textContent)).toEqual(["Ghi chú · 29 B"]);
    expect(banner.textContent).not.toContain(vi.canvas.fullHint);
    expect(editor()).toBeNull();
  });
});

describe("versions that went", () => {
  it("reads the list again when a version picked was folded away, and stays open", async () => {
    threeVersions(backend);
    await openPanel();
    await openHistory();
    backend.canvas.forget("a1", 1);

    await pick(1);

    expect(within(history()).getByRole("alert").textContent).toBe(vi.canvas.versionGone);
    expect(rows()).toEqual(["v4 · bạn · 4 phút · 15 B", "v2 · Ming · 4 phút · 9 B"]);
    expect(picked()).toMatch(/^v4 /);
  });

  it("reads the list again when the version to restore was folded away meanwhile", async () => {
    threeVersions(backend);
    await openPanel();
    await openHistory();
    await pick(1);
    backend.canvas.forget("a1", 1);

    fireEvent.click(within(history()).getByRole("button", { name: vi.canvas.restore }));
    await landed();

    expect(within(history()).getByRole("alert").textContent).toBe(vi.canvas.versionGone);
    expect(rows()).toHaveLength(2);
    expect(editor()).toBeNull();
  });

  it("takes a restore of a canvas deleted meanwhile for the deletion", async () => {
    threeVersions(backend);
    await openPanel();
    await openHistory();
    await pick(1);
    backend.canvas.onEvent = null;
    backend.canvas.remove("a1");

    fireEvent.click(within(history()).getByRole("button", { name: vi.canvas.restore }));
    await landed();

    expect(screen.queryByRole("region", { name: vi.canvas.historyTitle })).toBeNull();
    expect(screen.getByRole("alert").textContent).toBe(`${vi.canvas.gone} ${vi.canvas.goneHint}`);
    expect(editor()).toMatchObject({ value: "một\nhai\nbốn", readOnly: true });
  });
});
