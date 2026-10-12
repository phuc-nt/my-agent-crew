// A script may write a key again between the moment the list was read and the moment a
// person asks for the key's value. The value that comes back is then the later writing,
// and the row beside it has to be that same writing: its size, its time, and with them the
// namespace's size and its bar.
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { vi } from "../i18n/vi";
import type { FakeBackend } from "../test/fake-backend";
import { holdRequests, mountStore, namespaceCard, storeBackend, storeRequests } from "../test/script-store-screen";

const { scriptStore: words } = vi;

const T1 = "2026-10-12T01:00:00+00:00";
const T2 = "2026-10-12T02:00:00+00:00";
const T3 = "2026-10-12T03:00:00+00:00";
/** Ten characters, twenty-five and seven: each a JSON text, so each is set out as it is. */
const FIRST = "1234567890";
const SECOND = "1234567890123456789012345";
const THIRD = "7654321";

let backend: FakeBackend;

beforeEach(() => {
  backend = storeBackend();
  backend.scriptStore.keepText("coach", "job:brief", "seen", FIRST, T1);
});

const view = () => screen.findByRole("button", { name: words.viewLabel("seen") });
const box = () => screen.findByRole("group", { name: words.valueLabel("seen") });
const row = () => within(screen.getByTestId("script-store-entry"));
const listReads = () => storeRequests(backend).filter((asked) => asked === "GET /agents/coach/script-store").length;
/** How the namespace says its size: the key's four characters plus the value's. */
const size = (chars: number) => words.size(4 + chars, backend.scriptStore.limitChars);
/** Lets every answer already on its way land. */
const settled = () => act(async () => new Promise<void>((resolve) => setTimeout(resolve, 0)));

/** The row as the list first said it. */
async function listedAsFirst() {
  mountStore(backend);
  const press = await view();
  expect(row().getByText(words.entryChars(10), { exact: false })).toBeInTheDocument();
  expect(row().getByRole("time")).toHaveAttribute("datetime", T1);
  expect(namespaceCard("job:brief")).toHaveTextContent(size(10));
  return press;
}

describe("a value written again since the list was read", () => {
  it("is shown beside its own size and time: the list is read again, once", async () => {
    const press = await listedAsFirst();
    backend.scriptStore.keepText("coach", "job:brief", "seen", SECOND, T2);

    await userEvent.click(press);

    expect((await box()).textContent).toBe(SECOND);
    await waitFor(() => expect(row().getByRole("time")).toHaveAttribute("datetime", T2));
    expect(row().getByText(words.entryChars(25), { exact: false })).toBeInTheDocument();
    expect(row().queryByText(words.entryChars(10), { exact: false })).toBeNull();
    expect(namespaceCard("job:brief")).toHaveTextContent(size(25));
    // The box stays the key's value under the row the list then brought.
    expect((await box()).textContent).toBe(SECOND);
    await settled();
    expect(listReads()).toBe(2);
  });

  it("stays in its box while the list is being read again", async () => {
    const press = await listedAsFirst();
    backend.scriptStore.keepText("coach", "job:brief", "seen", SECOND, T2);
    const release = holdRequests(backend, /^GET [^?]*\/script-store$/);

    await userEvent.click(press);

    expect((await box()).textContent).toBe(SECOND);
    expect(row().getByRole("time")).toHaveAttribute("datetime", T1);
    release();
    await waitFor(() => expect(row().getByRole("time")).toHaveAttribute("datetime", T2));
    expect((await box()).textContent).toBe(SECOND);
  });

  it("is put away when the list read again shows a writing later than the value's", async () => {
    const press = await listedAsFirst();
    backend.scriptStore.keepText("coach", "job:brief", "seen", SECOND, T2);
    const release = holdRequests(backend, /^GET [^?]*\/script-store$/);
    await userEvent.click(press);
    expect((await box()).textContent).toBe(SECOND);

    backend.scriptStore.keepText("coach", "job:brief", "seen", THIRD, T3);
    release();

    await waitFor(() => expect(row().getByRole("time")).toHaveAttribute("datetime", T3));
    expect(screen.queryByTestId("script-store-value")).toBeNull();
    expect(row().getByTestId("script-store-preview")).toHaveTextContent(THIRD);
    expect(await view()).toHaveAttribute("aria-expanded", "false");
  });
});

describe("a value that is as the list said", () => {
  it("has the list read no second time", async () => {
    const press = await listedAsFirst();

    await userEvent.click(press);

    expect((await box()).textContent).toBe(FIRST);
    await settled();
    expect(listReads()).toBe(1);
    expect(row().getByRole("time")).toHaveAttribute("datetime", T1);
  });
});
