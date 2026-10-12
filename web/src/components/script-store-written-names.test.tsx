// A key is whatever a script chose, and a namespace goes by an id or by a title somebody
// typed. Two of them may differ only in what a page folds away or draws as nothing: a line
// break, a tab, a second space, a space at the end. Every place the store screen draws one,
// or says one in the name of a button, writes it out the same way, so the two read apart.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, type MockInstance, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import { coachAgent, fakeAgent, type FakeBackend } from "../test/fake-backend";
import { BRIEF, mountStore, shownKeys, storeBackend, takeOut } from "../test/script-store-screen";

const { scriptStore: words } = vi;

/** A key as it is kept, and as the screen writes it. */
const KEYS: Array<[string, string]> = [
  ["seen", "seen"],
  ["se en", "se en"],
  ["se  en", "se[U+0020][U+0020]en"],
  ["seen ", "seen[U+0020]"],
  [" seen", "[U+0020]seen"],
  ["se\nen", "se\\nen"],
  ["se\r\nen", "se\\r\\nen"],
  ["se\ten", "se\\ten"],
  ["se\u0085en", "se\\u0085en"],
  ["se en", "se\\u2028en"],
  ["se en", "se[U+00A0]en"],
  ["se​en", "se[U+200B]en"],
  ["se\\nen", "se\\\\nen"],
  ['se"en', 'se\\"en'],
];
/** In the order the server lists them. */
const LISTED = [...KEYS].sort(([one], [other]) => (one < other ? -1 : 1));
const WRITTEN = LISTED.map(([, written]) => written);

/** What a page makes of a text it draws, and a screen reader of a name it reads out. */
const folded = (text: string | null) => (text ?? "").trim().replace(/\s+/g, " ");

let backend: FakeBackend;
let confirm: MockInstance<typeof window.confirm>;

beforeEach(() => {
  backend = storeBackend();
  confirm = vitest.spyOn(window, "confirm").mockReturnValue(true);
});

afterEach(() => {
  vitest.restoreAllMocks();
});

const keepAll = async () => {
  for (const [key] of KEYS) backend.scriptStore.keep("coach", "job:brief", key, 1);
  mountStore(backend);
  await screen.findAllByTestId("script-store-entry");
  return screen.getAllByTestId("script-store-entry");
};
const labels = (rows: HTMLElement[], button: string) => rows.map((row) => row.querySelector(button)?.getAttribute("aria-label") ?? null);
const said = () => screen.getByRole("status").textContent;

describe("keys that differ only in what a page folds away or draws as nothing", () => {
  it("are each written their own way in their rows", async () => {
    await keepAll();

    expect(shownKeys()).toEqual(WRITTEN);
    expect(new Set(shownKeys().map(folded)).size).toBe(KEYS.length);
  });

  it("are each written that way in the name of the button that shows the value", async () => {
    const rows = await keepAll();

    expect(labels(rows, ".script-store-view")).toEqual(WRITTEN.map(words.viewLabel));
    expect(new Set(labels(rows, ".script-store-view").map(folded)).size).toBe(KEYS.length);
    // By the name a screen reader is given, in which white space is folded already.
    const two = screen.getByRole("button", { name: words.viewLabel("se[U+0020][U+0020]en") });
    const one = screen.getByRole("button", { name: words.viewLabel("se en") });
    expect(two).not.toBe(one);
  });

  it("are each written that way in the name of the button that deletes the key", async () => {
    const rows = await keepAll();

    expect(labels(rows, ".script-store-delete")).toEqual(WRITTEN.map(words.deleteKeyLabel));
    expect(new Set(labels(rows, ".script-store-delete").map(folded)).size).toBe(KEYS.length);
    expect(screen.getByRole("button", { name: words.deleteKeyLabel("seen[U+0020]") })).not.toBe(
      screen.getByRole("button", { name: words.deleteKeyLabel("seen") }),
    );
  });

  it.each(["seen ", "se\nen", "se  en"])("are written that way over a value that is open and on the button that closes it (%j)", async (key) => {
    const rows = await keepAll();
    const at = LISTED.findIndex(([kept]) => kept === key);
    const row = within(rows[at]);

    await userEvent.click(row.getByRole("button", { name: words.viewLabel(WRITTEN[at]) }));

    expect(await row.findByRole("group", { name: words.valueLabel(WRITTEN[at]) })).toBe(row.getByTestId("script-store-value"));
    expect(row.getByTestId("script-store-value").getAttribute("aria-label")).toBe(words.valueLabel(WRITTEN[at]));
    expect(row.getByRole("button", { name: words.hideLabel(WRITTEN[at]) })).toBe(rows[at].querySelector(".script-store-view"));
    expect(rows[at].querySelector(".script-store-view")?.getAttribute("aria-label")).toBe(words.hideLabel(WRITTEN[at]));
  });

  it("are asked about, and said to have gone, in the writing their rows have", async () => {
    backend.scriptStore.keep("coach", "job:brief", "se\nen ", 1);
    mountStore(backend);
    const row = await screen.findByTestId("script-store-entry");
    const shown = row.querySelector(".script-store-key")?.textContent;
    expect(shown).toBe("se\\nen[U+0020]");

    await userEvent.click(row.querySelector(".script-store-delete") as HTMLElement);

    expect(confirm.mock.calls).toEqual([[`Xoá khoá "${shown}" của ${BRIEF}? Không thể hoàn tác.`]]);
    await waitFor(() => expect(said()).toBe(`Đã xoá khoá "${shown}".`));
  });

  it("are said to be gone in the writing their rows had", async () => {
    backend.scriptStore.keep("coach", "job:brief", " se  en", 1);
    mountStore(backend);
    const row = await screen.findByTestId("script-store-entry");
    const shown = row.querySelector(".script-store-key")?.textContent;
    expect(shown).toBe("[U+0020]se[U+0020][U+0020]en");
    takeOut(backend, "coach", "job:brief", " se  en");

    await userEvent.click(row.querySelector(".script-store-view") as HTMLElement);

    await waitFor(() => expect(said()).toBe(`Khoá "${shown}" không còn nữa; đã tải lại danh sách.`));
  });
});

describe("namespaces whose names differ only in what a page folds away or draws as nothing", () => {
  /** What each card on screen says of its namespace, by the name the namespace is stored under. */
  const cards = () =>
    Object.fromEntries(
      screen.getAllByTestId("script-store-namespace").map((card) => [
        card.dataset.namespace,
        {
          name: card.querySelector(".script-store-name")?.textContent ?? null,
          stored: card.querySelector(".script-store-stored")?.textContent ?? null,
          all: card.querySelector(".script-store-delete-all")?.getAttribute("aria-label") ?? null,
          size: card.querySelector('[role="progressbar"]')?.getAttribute("aria-label") ?? null,
        },
      ]),
    );
  const card = (name: string, stored: string | null, phrase: string) => ({ name, stored, all: words.deleteAllLabel(phrase), size: words.sizeLabel(phrase) });

  it("are each written their own way in the heading, under it, and in the names of the bar and the button", async () => {
    const [brief] = coachAgent.schedules;
    backend.agents = [fakeAgent, { ...coachAgent, schedules: [brief, { ...brief, id: "tin", name: "Tin  sáng" }, { ...brief, id: "tin\t", name: "Tin sáng" }] }];
    const chat = backend.create({ agent_id: "coach", title: "Đơn\nmới" });
    for (const namespace of ["job:tin", "job:tin\t", "job:a\nb", "job:a b ", `conv:${chat.id}`, "kho  cũ", "kho cũ", "kho\r\ncũ"]) {
      backend.scriptStore.keep("coach", namespace, "k", 1);
    }
    mountStore(backend);
    await screen.findAllByTestId("script-store-entry");

    expect(cards()).toEqual({
      // A schedule and a conversation go by their names; the stored name stands under each.
      "job:tin": card("Tin[U+0020][U+0020]sáng", "job:tin", 'lịch "Tin[U+0020][U+0020]sáng"'),
      "job:tin\t": card("Tin sáng", "job:tin\\t", 'lịch "Tin sáng"'),
      [`conv:${chat.id}`]: card("Đơn\\nmới", `conv:${chat.id}`, 'cuộc trò chuyện "Đơn\\nmới"'),
      // A schedule that is gone goes by its id.
      "job:a\nb": card("a\\nb", "job:a\\nb", 'lịch "a\\nb"'),
      "job:a b ": card("a b[U+0020]", "job:a b[U+0020]", 'lịch "a b[U+0020]"'),
      // Neither a schedule's nor a conversation's: the stored name is the name.
      "kho  cũ": card("kho[U+0020][U+0020]cũ", null, '"kho[U+0020][U+0020]cũ"'),
      "kho cũ": card("kho cũ", null, '"kho cũ"'),
      "kho\r\ncũ": card("kho\\r\\ncũ", null, '"kho\\r\\ncũ"'),
    });
    // The way to a schedule's row is named as the heading is written.
    expect(screen.getByRole("link", { name: "Tin[U+0020][U+0020]sáng" })).not.toBe(screen.getByRole("link", { name: "Tin sáng" }));
  });

  it("are asked about, and said to be emptied, in the writing the heading has", async () => {
    backend.scriptStore.keep("coach", "kho\ncũ  ", "k", 1);
    mountStore(backend);
    await screen.findByTestId("script-store-entry");
    const shown = document.querySelector(".script-store-name")?.textContent;
    expect(shown).toBe("kho\\ncũ[U+0020][U+0020]");

    await userEvent.click(screen.getByRole("button", { name: words.deleteAllLabel(`"${shown}"`) }));

    expect(confirm.mock.calls).toEqual([[`Xoá cả 1 khoá của "${shown}"? Không thể hoàn tác.`]]);
    await waitFor(() => expect(said()).toBe(`Đã xoá 1 khoá của "${shown}".`));
  });
});
