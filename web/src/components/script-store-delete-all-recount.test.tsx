// "Delete all N keys" names a number, and a script may have written since the list on
// screen was read. The list is read again before the question, and the question is asked
// about the namespace as that read found it.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, type MockInstance, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import type { FakeBackend } from "../test/fake-backend";
import { BRIEF, holdRequests, mountStore, namespaceCard as card, shownKeys as keys, storeBackend, storeRequests, takeOut } from "../test/script-store-screen";

const { scriptStore: words } = vi;
const LIST = "GET /agents/coach/script-store";

let backend: FakeBackend;
let confirm: MockInstance<typeof window.confirm>;

beforeEach(() => {
  backend = storeBackend();
  backend.scriptStore.keep("coach", "job:brief", "a", 1).keep("coach", "job:brief", "b", 2);
  confirm = vitest.spyOn(window, "confirm").mockReturnValue(true);
});

afterEach(() => {
  vitest.restoreAllMocks();
});

const deleteAll = (where = BRIEF) => screen.findByRole("button", { name: words.deleteAllLabel(where) });
const asked = () => storeRequests(backend);
const deletes = () => asked().filter((request) => request.startsWith("DELETE "));
const said = () => screen.getByRole("status");
/** Three more keys written behind the screen's back, as a script's run would. */
const writeThreeMore = () => backend.scriptStore.keep("coach", "job:brief", "c", 3).keep("coach", "job:brief", "d", 4).keep("coach", "job:brief", "e", 5);

describe("the question before a whole namespace is deleted", () => {
  it("names how many keys the server has now, not how many the list showed", async () => {
    mountStore(backend);
    const press = await deleteAll();
    expect(keys()).toEqual(["a", "b"]);
    writeThreeMore();

    await userEvent.click(press);

    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1));
    expect(confirm).toHaveBeenCalledWith(words.deleteAllConfirm(5, BRIEF));
    await waitFor(() => expect(said()).toHaveTextContent(words.deletedAll(5, BRIEF)));
    // Read again before the question, and once more for what the delete left.
    expect(asked()).toEqual([LIST, LIST, "DELETE /agents/coach/script-store?namespace=job%3Abrief", LIST]);
    expect(backend.scriptStore.keys("coach", "job:brief")).toEqual([]);
  });

  it("leaves the list as it was just read on screen when the person says no", async () => {
    confirm.mockReturnValue(false);
    mountStore(backend);
    const press = await deleteAll();
    writeThreeMore();

    await userEvent.click(press);

    await waitFor(() => expect(keys()).toEqual(["a", "b", "c", "d", "e"]));
    expect(confirm).toHaveBeenCalledWith(words.deleteAllConfirm(5, BRIEF));
    expect(deletes()).toEqual([]);
    expect(said()).toBeEmptyDOMElement();
  });

  it("names the namespace as it is called now", async () => {
    const chat = backend.create({ agent_id: "coach", title: "Đơn mới" });
    backend.scriptStore.keep("coach", `conv:${chat.id}`, "draft", "nháp");
    mountStore(backend);
    const press = await deleteAll('cuộc trò chuyện "Đơn mới"');
    chat.title = "Đơn đã giao";

    await userEvent.click(press);

    await waitFor(() => expect(confirm).toHaveBeenCalledWith(words.deleteAllConfirm(1, 'cuộc trò chuyện "Đơn đã giao"')));
    await waitFor(() => expect(said()).toHaveTextContent(words.deletedAll(1, 'cuộc trò chuyện "Đơn đã giao"')));
  });

  it("is not asked for one key: that question names no number", async () => {
    mountStore(backend);

    await userEvent.click(await screen.findByRole("button", { name: words.deleteKeyLabel("a") }));

    await waitFor(() => expect(keys()).toEqual(["b"]));
    expect(asked()).toEqual([LIST, "DELETE /agents/coach/script-store?namespace=job%3Abrief&key=a", LIST]);
  });
});

describe("a namespace that is gone by the time its delete is pressed", () => {
  it("is said to have nothing left, and nobody is asked anything", async () => {
    const chat = backend.create({ agent_id: "coach", title: "Đơn mới" });
    backend.scriptStore.keep("coach", `conv:${chat.id}`, "draft", "nháp");
    mountStore(backend);
    const press = await deleteAll();
    takeOut(backend, "coach", "job:brief");
    const before = asked().length;

    await userEvent.click(press);

    await waitFor(() => expect(said()).toHaveTextContent(words.nothingDeleted));
    expect(confirm).not.toHaveBeenCalled();
    expect(asked().slice(before)).toEqual([LIST]);
    expect(card("job:brief")).toBeNull();
    expect(keys()).toEqual(["draft"]);
    // The button that was pressed went with its namespace.
    await waitFor(() => expect(within(card(`conv:${chat.id}`)).getByRole("heading")).toHaveFocus());
  });

  it("leaves the empty state and the keyboard on the agent's select when it was the last one", async () => {
    mountStore(backend);
    const press = await deleteAll();
    takeOut(backend, "coach", "job:brief");

    await userEvent.click(press);

    expect(await screen.findByTestId("empty-state")).toHaveTextContent(words.empty);
    expect(said()).toHaveTextContent(words.nothingDeleted);
    expect(confirm).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByRole("combobox", { name: vi.agents })).toHaveFocus());
  });
});

describe("while the list is read again for the question", () => {
  const listRead = /^GET [^?]*\/script-store$/;

  it("a second press, and a press on one of its keys, ask nothing more", async () => {
    mountStore(backend);
    const press = await deleteAll();
    const release = holdRequests(backend, listRead);

    await userEvent.click(press);
    await userEvent.click(press);
    await userEvent.click(screen.getByRole("button", { name: words.deleteKeyLabel("a") }));
    expect(confirm).not.toHaveBeenCalled();
    release();

    expect(await screen.findByTestId("empty-state")).toBeInTheDocument();
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(deletes()).toEqual(["DELETE /agents/coach/script-store?namespace=job%3Abrief"]);
  });

  it("the person may leave for another agent, and is then asked nothing", async () => {
    const { show } = mountStore(backend);
    const press = await deleteAll();
    const release = holdRequests(backend, listRead);

    await userEvent.click(press);
    show("default");
    release();

    await screen.findByTestId("empty-state");
    // Time for the held read to come back to a screen that is no longer there.
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(confirm).not.toHaveBeenCalled();
    expect(deletes()).toEqual([]);
    expect(backend.scriptStore.keys("coach", "job:brief")).toEqual(["a", "b"]);
  });

  it("a read the server refuses is said under the namespace, asks nothing, and the next press asks", async () => {
    mountStore(backend);
    const press = await deleteAll();
    backend.scriptStore.refuse.list = { status: 409, detail: "Kho đang bận, thử lại sau." };

    await userEvent.click(press);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Kho đang bận, thử lại sau.");
    expect(alert.closest('[data-namespace="job:brief"]')).not.toBeNull();
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(confirm).not.toHaveBeenCalled();
    expect(deletes()).toEqual([]);
    expect(keys()).toEqual(["a", "b"]);
    expect(press).toHaveFocus();

    backend.scriptStore.refuse.list = undefined;
    await userEvent.click(press);

    await waitFor(() => expect(confirm).toHaveBeenCalledWith(words.deleteAllConfirm(2, BRIEF)));
    expect(await screen.findByTestId("empty-state")).toBeInTheDocument();
  });
});
