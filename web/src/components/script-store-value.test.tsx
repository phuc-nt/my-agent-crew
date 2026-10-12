import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import type { FakeBackend } from "../test/fake-backend";
import { holdRequests, mountStore, storeBackend, storeRequests, takeOut } from "../test/script-store-screen";

const { scriptStore: words } = vi;

let backend: FakeBackend;

beforeEach(() => {
  backend = storeBackend();
});

afterEach(() => {
  vitest.restoreAllMocks();
});

const view = (key: string) => screen.findByRole("button", { name: words.viewLabel(key) });
const box = (key: string) => screen.findByRole("group", { name: words.valueLabel(key) });
const row = (key: string) => screen.getByText(key, { selector: ".script-store-key" }).closest("li") as HTMLElement;
const valueReads = () => storeRequests(backend).filter((asked) => asked.includes("/value?"));

describe("a key's whole value", () => {
  it("is read only when asked for, set out as JSON in a box of its own, and put away again", async () => {
    backend.scriptStore.keep("coach", "job:brief", "seen", { ids: ["a1", "b2"], n: 2 });
    mountStore(backend);
    const press = await view("seen");
    expect(press).toHaveAttribute("aria-expanded", "false");
    expect(valueReads()).toEqual([]);

    await userEvent.click(press);

    const shown = await box("seen");
    expect(shown.textContent).toBe('{\n  "ids": [\n    "a1",\n    "b2"\n  ],\n  "n": 2\n}');
    expect(valueReads()).toEqual(["GET /agents/coach/script-store/value?namespace=job%3Abrief&key=seen"]);
    // A value taller than its box is scrolled from the keyboard, so the box takes it.
    expect(shown).toHaveAttribute("tabindex", "0");
    const hide = screen.getByRole("button", { name: words.hideLabel("seen") });
    expect(hide).toHaveAttribute("aria-expanded", "true");
    expect(hide).toHaveAttribute("aria-controls", shown.id);
    expect(screen.queryByTestId("script-store-preview")).toBeNull();
    expect(screen.queryByText(words.valueRaw)).toBeNull();

    await userEvent.click(hide);
    expect(screen.queryByTestId("script-store-value")).toBeNull();
    expect(screen.getByTestId("script-store-preview")).toHaveTextContent('{"ids":["a1","b2"],"n":2}');
    expect(await view("seen")).toHaveAttribute("aria-expanded", "false");
  });

  it("is shown whole, past where the list cut it", async () => {
    const long = "x".repeat(300);
    backend.scriptStore.keep("coach", "job:brief", "long", long);
    mountStore(backend);
    expect(await screen.findByTestId("script-store-preview")).toHaveTextContent(`"${"x".repeat(199)}…`);

    await userEvent.click(await view("long"));

    expect((await box("long")).textContent).toBe(`"${long}"`);
  });

  it("is shown as it is kept when it is not JSON, with a line saying so", async () => {
    backend.scriptStore.keepText("coach", "job:brief", "note", "đơn hàng: {chưa xong\n  hai dòng");
    mountStore(backend);

    await userEvent.click(await view("note"));

    expect((await box("note")).textContent).toBe("đơn hàng: {chưa xong\n  hai dòng");
    expect(screen.getByText(words.valueRaw)).toBeInTheDocument();
  });

  it("has the characters nobody would see written out, in the key and in the value, and is asked for by the key as kept", async () => {
    backend.scriptStore.keep("coach", "job:brief", "k\u202Ey", "a\u200Bb");
    mountStore(backend);

    await userEvent.click(await view("k[U+202E]y"));

    expect((await box("k[U+202E]y")).textContent).toBe('"a[U+200B]b"');
    expect(valueReads()).toEqual([`GET /agents/coach/script-store/value?namespace=job%3Abrief&key=${encodeURIComponent("k\u202Ey")}`]);
    await userEvent.click(screen.getByRole("button", { name: words.hideLabel("k[U+202E]y") }));
    expect(screen.getByTestId("script-store-preview")).toHaveTextContent('"a[U+200B]b"');
  });

  it("says it is being read while the server answers", async () => {
    backend.scriptStore.keep("coach", "job:brief", "seen", 1);
    const release = holdRequests(backend, /\/value\?/);
    mountStore(backend);

    await userEvent.click(await view("seen"));
    expect(screen.getByText(words.valueLoading)).toBeInTheDocument();
    expect(screen.getByTestId("script-store-preview")).toBeInTheDocument();

    release();
    expect(await box("seen")).toHaveTextContent("1");
    expect(screen.queryByText(words.valueLoading)).toBeNull();
  });

  it("stays put away when it comes after the person closed it", async () => {
    backend.scriptStore.keep("coach", "job:brief", "seen", 1);
    const release = holdRequests(backend, /\/value\?/);
    mountStore(backend);
    await userEvent.click(await view("seen"));
    await userEvent.click(screen.getByRole("button", { name: words.hideLabel("seen") }));
    expect(screen.queryByText(words.valueLoading)).toBeNull();

    release();
    await waitFor(() => expect(valueReads()).toHaveLength(1));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(screen.queryByTestId("script-store-value")).toBeNull();
    expect(await view("seen")).toHaveAttribute("aria-expanded", "false");
  });

  it("when the key is gone: says so, takes the row out, reads the list again and moves the keyboard to the next key", async () => {
    backend.scriptStore.keep("coach", "job:brief", "a", 1).keep("coach", "job:brief", "b", 2).keep("coach", "job:brief", "c", 3);
    mountStore(backend);
    const press = await view("b");
    takeOut(backend, "coach", "job:brief", "b");
    // Written by a script since the list was read: only reading the list again shows it.
    backend.scriptStore.keep("coach", "job:brief", "d", 4);

    await userEvent.click(press);

    expect(await screen.findByText(words.gone('"b"'))).toHaveAttribute("role", "status");
    expect(screen.queryByRole("button", { name: words.viewLabel("b") })).toBeNull();
    expect(await view("d")).toBeInTheDocument();
    expect(storeRequests(backend).filter((asked) => asked === "GET /agents/coach/script-store")).toHaveLength(2);
    // The key that took its place.
    const next = await view("c");
    await waitFor(() => expect(next).toHaveFocus());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("when it cannot be read: shows the usual error in the row, keeps the row, and reads again when asked", async () => {
    backend.scriptStore.keep("coach", "job:brief", "seen", 1).keep("coach", "job:brief", "other", 2);
    backend.scriptStore.refuse.value = { status: 500, detail: "boom" };
    mountStore(backend);

    await userEvent.click(await view("seen"));

    const alert = await within(row("seen")).findByRole("alert");
    expect(alert).toHaveTextContent(vi.requestErrors.server(500));
    expect(within(row("other")).queryByRole("alert")).toBeNull();
    expect(within(row("seen")).getByTestId("script-store-preview")).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeEmptyDOMElement();

    backend.scriptStore.refuse = {};
    await userEvent.click(within(alert).getByRole("button", { name: vi.retry }));
    expect(await box("seen")).toHaveTextContent("1");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("is put away once the key was written again, so an old value is never read as the key's", async () => {
    backend.scriptStore.keep("coach", "job:brief", "seen", ["old"]).keep("coach", "job:brief", "spare", 0);
    mountStore(backend);
    await userEvent.click(await view("seen"));
    expect(await box("seen")).toHaveTextContent('[ "old" ]');

    backend.scriptStore.keep("coach", "job:brief", "seen", ["new"], "2026-10-12T02:00:00+00:00");
    // Deleting another key reads the list again.
    vitest.spyOn(window, "confirm").mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: words.deleteKeyLabel("spare") }));

    await waitFor(() => expect(within(screen.getByTestId("script-store-entry")).getByTestId("script-store-preview")).toHaveTextContent('["new"]'));
    expect(screen.queryByTestId("script-store-value")).toBeNull();
    expect(await view("seen")).toHaveAttribute("aria-expanded", "false");
  });
});
