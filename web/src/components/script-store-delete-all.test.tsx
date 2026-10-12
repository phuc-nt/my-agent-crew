import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, type MockInstance, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import type { FakeBackend } from "../test/fake-backend";
import { BRIEF, holdRequests, mountStore, namespaceCard as card, shownKeys as keys, storeBackend, storeRequests } from "../test/script-store-screen";

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

const deleteKey = (key: string) => screen.findByRole("button", { name: words.deleteKeyLabel(key) });
const deleteAll = (where: string) => screen.findByRole("button", { name: words.deleteAllLabel(where) });
const deletes = () => storeRequests(backend).filter((asked) => asked.startsWith("DELETE "));
const said = () => screen.getByRole("status");

describe("deleting a whole namespace", () => {
  it("asks first, naming how many keys go, deletes them all, and moves the keyboard to the namespace that took its place", async () => {
    const chat = backend.create({ agent_id: "coach", title: "Đơn mới" });
    backend.scriptStore.keep("coach", `conv:${chat.id}`, "draft", "nháp");
    mountStore(backend);

    await userEvent.click(await deleteAll(BRIEF));

    expect(confirm).toHaveBeenCalledWith(words.deleteAllConfirm(3, BRIEF));
    await waitFor(() => expect(keys()).toEqual(["draft"]));
    expect(deletes()).toEqual(["DELETE /agents/coach/script-store?namespace=job%3Abrief"]);
    expect(backend.scriptStore.keys("coach", "job:brief")).toEqual([]);
    expect(backend.scriptStore.keys("coach", `conv:${chat.id}`)).toEqual(["draft"]);
    expect(said()).toHaveTextContent(words.deletedAll(3, BRIEF));
    await waitFor(() => expect(within(card(`conv:${chat.id}`)).getByRole("heading")).toHaveFocus());
  });

  it("leaves the empty state and moves the keyboard to the agent's select when it was the last one", async () => {
    mountStore(backend);

    await userEvent.click(await deleteAll(BRIEF));

    expect(await screen.findByTestId("empty-state")).toHaveTextContent(words.empty);
    await waitFor(() => expect(screen.getByRole("combobox", { name: vi.agents })).toHaveFocus());
  });

  it("asks about no key of a namespace that is going whole", async () => {
    const release = holdRequests(backend, /^DELETE /);
    mountStore(backend);

    await userEvent.click(await deleteAll(BRIEF));
    await userEvent.click(await deleteKey("b"));
    await userEvent.click(await deleteAll(BRIEF));
    release();

    expect(await screen.findByTestId("empty-state")).toBeInTheDocument();
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(deletes()).toEqual(["DELETE /agents/coach/script-store?namespace=job%3Abrief"]);
  });

  it("asks nothing of the server when the person says no to a namespace", async () => {
    confirm.mockReturnValue(false);
    mountStore(backend);

    await userEvent.click(await deleteAll(BRIEF));

    expect(deletes()).toEqual([]);
    expect(keys()).toEqual(["a", "b", "c"]);
  });

  it("shows the server's own words for a refusal under the namespace, not in a row, and moves nothing", async () => {
    backend.scriptStore.refuse.remove = { status: 409, detail: "Kho đang bận, thử lại sau." };
    mountStore(backend);
    const press = await deleteAll(BRIEF);

    await userEvent.click(press);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Kho đang bận, thử lại sau.");
    expect(alert.closest("li")).toBeNull();
    expect(alert.closest('[data-namespace="job:brief"]')).not.toBeNull();
    expect(keys()).toEqual(["a", "b", "c"]);
    expect(press).toHaveFocus();
    expect(said()).toBeEmptyDOMElement();
  });
});
