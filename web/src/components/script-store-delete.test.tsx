import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, type MockInstance, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import type { FakeBackend } from "../test/fake-backend";
import { BRIEF, holdRequests, mountStore, namespaceCard as card, shownKeys as keys, storeBackend, storeRequests, takeOut } from "../test/script-store-screen";

const { scriptStore: words } = vi;

let backend: FakeBackend;
let confirm: MockInstance<typeof window.confirm>;

beforeEach(() => {
  backend = storeBackend();
  backend.scriptStore.keep("coach", "job:brief", "a", 1).keep("coach", "job:brief", "b", 2).keep("coach", "job:brief", "c", 3);
  confirm = vitest.spyOn(window, "confirm").mockReturnValue(true);
});

afterEach(() => {
  vitest.restoreAllMocks();
});

const view = (key: string) => screen.getByRole("button", { name: words.viewLabel(key) });
const deleteKey = (key: string) => screen.findByRole("button", { name: words.deleteKeyLabel(key) });
const row = (key: string) => screen.getByText(key, { selector: ".script-store-key" }).closest("li") as HTMLElement;
const deletes = () => storeRequests(backend).filter((asked) => asked.startsWith("DELETE "));
const lists = () => storeRequests(backend).filter((asked) => asked === "GET /agents/coach/script-store");
const said = () => screen.getByRole("status");

describe("deleting one key", () => {
  it("asks first, deletes that key alone, says what went and reads the list again", async () => {
    mountStore(backend);

    await userEvent.click(await deleteKey("b"));

    expect(confirm).toHaveBeenCalledWith(words.deleteKeyConfirm('"b"', BRIEF));
    await waitFor(() => expect(keys()).toEqual(["a", "c"]));
    expect(deletes()).toEqual(["DELETE /agents/coach/script-store?namespace=job%3Abrief&key=b"]);
    expect(backend.scriptStore.keys("coach", "job:brief")).toEqual(["a", "c"]);
    expect(said()).toHaveTextContent(words.deletedKey('"b"'));
    // a + 1 and c + 3: the size follows the keys that are left.
    expect(within(card("job:brief")).getByText(`${words.keyCount(2)} · ${words.size(4, 262_144)}`)).toBeInTheDocument();
    await waitFor(() => expect(lists()).toHaveLength(2));
  });

  it("asks nothing of the server when the person says no", async () => {
    confirm.mockReturnValue(false);
    mountStore(backend);

    await userEvent.click(await deleteKey("b"));

    expect(confirm).toHaveBeenCalledTimes(1);
    expect(deletes()).toEqual([]);
    expect(keys()).toEqual(["a", "b", "c"]);
    expect(said()).toBeEmptyDOMElement();
  });

  it("moves the keyboard to the key that took its place, and to the last key when none did", async () => {
    mountStore(backend);

    await userEvent.click(await deleteKey("b"));
    await waitFor(() => expect(view("c")).toHaveFocus());

    await userEvent.click(await deleteKey("c"));
    await waitFor(() => expect(view("a")).toHaveFocus());
  });

  it("takes the namespace with its last key, and moves the keyboard to the heading of the one that took its place", async () => {
    backend.scriptStore.keep("coach", "job:only", "k", 1).keep("coach", "misc", "k", 1);
    mountStore(backend);

    await deleteKey("a");
    await userEvent.click(within(card("job:only")).getByRole("button", { name: words.deleteKeyLabel("k") }));

    await waitFor(() => expect(card("job:only")).toBeNull());
    await waitFor(() => expect(within(card("misc")).getByRole("heading")).toHaveFocus());
  });

  it("shows why the server refused in the row it was asked in, and moves nothing", async () => {
    backend.scriptStore.refuse.remove = { status: 500, detail: "database is locked" };
    mountStore(backend);
    const press = await deleteKey("b");

    await userEvent.click(press);

    expect(await within(row("b")).findByRole("alert")).toHaveTextContent(vi.requestErrors.server(500));
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(keys()).toEqual(["a", "b", "c"]);
    expect(said()).toBeEmptyDOMElement();
    expect(press).toHaveFocus();
    expect(lists()).toHaveLength(1);

    // Asked again once the server is well: the refusal goes with the row.
    backend.scriptStore.refuse = {};
    await userEvent.click(press);
    await waitFor(() => expect(keys()).toEqual(["a", "c"]));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says nothing was left to delete when the server no longer had the key, and still takes the row out", async () => {
    mountStore(backend);
    const press = await deleteKey("b");
    takeOut(backend, "coach", "job:brief", "b");

    await userEvent.click(press);

    await waitFor(() => expect(said()).toHaveTextContent(words.nothingDeleted));
    expect(keys()).toEqual(["a", "c"]);
  });

  it("asks the person and the server once when the same delete is pressed again before it is answered", async () => {
    const release = holdRequests(backend, /^DELETE /);
    mountStore(backend);

    await userEvent.click(await deleteKey("b"));
    await userEvent.click(await deleteKey("b"));
    release();

    await waitFor(() => expect(keys()).toEqual(["a", "c"]));
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(deletes()).toEqual(["DELETE /agents/coach/script-store?namespace=job%3Abrief&key=b"]);
    expect(said()).toHaveTextContent(words.deletedKey('"b"'));
  });

  it("lets another key go while the first delete is unanswered", async () => {
    const release = holdRequests(backend, /^DELETE /);
    mountStore(backend);

    await userEvent.click(await deleteKey("b"));
    await userEvent.click(await deleteKey("c"));
    release();

    await waitFor(() => expect(keys()).toEqual(["a"]));
    expect(deletes()).toHaveLength(2);
    expect(backend.scriptStore.keys("coach", "job:brief")).toEqual(["a"]);
  });

  it("leaves the keyboard where the person took it while the server was answering", async () => {
    const release = holdRequests(backend, /^DELETE /);
    mountStore(backend);
    await userEvent.click(await deleteKey("b"));
    const elsewhere = screen.getByRole("combobox", { name: vi.agents });
    elsewhere.focus();

    release();

    await waitFor(() => expect(said()).toHaveTextContent(words.deletedKey('"b"')));
    await waitFor(() => expect(lists()).toHaveLength(2));
    expect(elsewhere).toHaveFocus();
  });

  it("keeps what it had on screen, without the key, when reading the list again fails", async () => {
    mountStore(backend);
    const press = await deleteKey("b");
    backend.scriptStore.refuse.list = { status: 500, detail: "boom" };

    await userEvent.click(press);

    expect(await screen.findByRole("alert")).toHaveTextContent(vi.requestErrors.server(500));
    expect(keys()).toEqual(["a", "c"]);
    expect(said()).toHaveTextContent(words.deletedKey('"b"'));
  });
});
