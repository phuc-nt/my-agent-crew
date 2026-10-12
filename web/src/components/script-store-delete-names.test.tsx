// Names go into the question a delete asks and into the line that says what went. A key is
// whatever a script chose and a title whatever a person typed, so each stands there between
// quotes, escaped and cut to length, and the sentence around it keeps its shape.
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, type MockInstance, vi as vitest } from "vitest";
import type { FakeBackend } from "../test/fake-backend";
import { mountStore, storeBackend, storeRequests, takeOut } from "../test/script-store-screen";

let backend: FakeBackend;
let confirm: MockInstance<typeof window.confirm>;

beforeEach(() => {
  backend = storeBackend();
  confirm = vitest.spyOn(window, "confirm").mockReturnValue(true);
});

afterEach(() => {
  vitest.restoreAllMocks();
});

const asked = () => confirm.mock.calls.map(([question]) => question);
const said = () => screen.getByRole("status").textContent;
const deletes = () => storeRequests(backend).filter((request) => request.startsWith("DELETE "));
const named = (namespace: string, key?: string) => new URLSearchParams(key === undefined ? { namespace } : { namespace, key }).toString();
// Each screen below holds one namespace with one key, so a button is found by where it
// stands: its label holds the name as it is kept, which is what is under test.
const press = async (button: "view" | "delete" | "delete-all") => {
  const entry = await screen.findByTestId("script-store-entry");
  const found = button === "delete-all" ? document.querySelector(".script-store-delete-all") : entry.querySelector(`.script-store-${button}`);
  await userEvent.click(found as HTMLElement);
};

describe("a key named in the delete question and in the line that follows", () => {
  it("is on one line between its quotes, with its own quote and line break escaped", async () => {
    const key = 'a"\nXoá cả kho?';
    backend.scriptStore.keep("coach", "job:brief", key, 1);
    mountStore(backend);

    await press("delete");

    expect(asked()).toEqual(['Xoá khoá "a\\"\\nXoá cả kho?" của lịch "Bản tin sáng"? Không thể hoàn tác.']);
    await waitFor(() => expect(said()).toBe('Đã xoá khoá "a\\"\\nXoá cả kho?".'));
    // The server is asked for the key as it is kept.
    expect(deletes()).toEqual([`DELETE /agents/coach/script-store?${named("job:brief", key)}`]);
  });

  it("is cut at eighty characters, and deleted whole", async () => {
    const key = "k".repeat(300);
    backend.scriptStore.keep("coach", "job:brief", key, 1);
    mountStore(backend);

    await press("delete");

    expect(asked()).toEqual([`Xoá khoá "${"k".repeat(80)}…" của lịch "Bản tin sáng"? Không thể hoàn tác.`]);
    await waitFor(() => expect(said()).toBe(`Đã xoá khoá "${"k".repeat(80)}…".`));
    expect(deletes()).toEqual([`DELETE /agents/coach/script-store?${named("job:brief", key)}`]);
  });

  it("has the spaces it ends with and what nobody would see written out between its quotes", async () => {
    backend.scriptStore.keep("coach", "job:brief", "seen\u200B  ", 1);
    mountStore(backend);

    await press("delete");

    expect(asked()).toEqual(['Xoá khoá "seen[U+200B][U+0020][U+0020]" của lịch "Bản tin sáng"? Không thể hoàn tác.']);
    await waitFor(() => expect(said()).toBe('Đã xoá khoá "seen[U+200B][U+0020][U+0020]".'));
  });

  it("is named the same way in the line that says it is gone", async () => {
    const key = 'a"\nb';
    backend.scriptStore.keep("coach", "job:brief", key, 1);
    mountStore(backend);
    await screen.findByTestId("script-store-entry");
    takeOut(backend, "coach", "job:brief", key);

    await press("view");

    await waitFor(() => expect(said()).toBe('Khoá "a\\"\\nb" không còn nữa; đã tải lại danh sách.'));
  });
});

describe("a schedule or a conversation named in the delete question and in the line that follows", () => {
  it("is named by its title without the spaces the title ends with", async () => {
    const chat = backend.create({ agent_id: "coach", title: "Đơn mới   " });
    backend.scriptStore.keep("coach", `conv:${chat.id}`, "draft", 1);
    mountStore(backend);

    await press("delete-all");

    expect(asked()).toEqual(['Xoá cả 1 khoá của cuộc trò chuyện "Đơn mới"? Không thể hoàn tác.']);
    await waitFor(() => expect(said()).toBe('Đã xoá 1 khoá của cuộc trò chuyện "Đơn mới".'));
  });

  it("has its title's quote and line break escaped, in the question about one key too", async () => {
    const chat = backend.create({ agent_id: "coach", title: 'Đơn "mới"\nXoá cả kho' });
    backend.scriptStore.keep("coach", `conv:${chat.id}`, "draft", 1);
    mountStore(backend);

    await press("delete");

    expect(asked()).toEqual(['Xoá khoá "draft" của cuộc trò chuyện "Đơn \\"mới\\"\\nXoá cả kho"? Không thể hoàn tác.']);
  });

  it("is cut at eighty characters when its title is longer", async () => {
    const chat = backend.create({ agent_id: "coach", title: "t".repeat(300) });
    backend.scriptStore.keep("coach", `conv:${chat.id}`, "draft", 1);
    mountStore(backend);

    await press("delete-all");

    expect(asked()).toEqual([`Xoá cả 1 khoá của cuộc trò chuyện "${"t".repeat(80)}…"? Không thể hoàn tác.`]);
    await waitFor(() => expect(said()).toBe(`Đã xoá 1 khoá của cuộc trò chuyện "${"t".repeat(80)}…".`));
  });

  it("is its stored name between quotes, written out, when it is neither", async () => {
    backend.scriptStore.keep("coach", "kho\ncũ  ", "draft", 1);
    mountStore(backend);

    await press("delete-all");

    expect(asked()).toEqual(['Xoá cả 1 khoá của "kho\\ncũ[U+0020][U+0020]"? Không thể hoàn tác.']);
    await waitFor(() => expect(said()).toBe('Đã xoá 1 khoá của "kho\\ncũ[U+0020][U+0020]".'));
    expect(deletes()).toEqual([`DELETE /agents/coach/script-store?${named("kho\ncũ  ")}`]);
  });
});
