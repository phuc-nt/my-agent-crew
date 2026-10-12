// A box closed and opened again before the server answered has two reads of the one key
// under way. Whichever lands first, the box is the later read's: that is the one the person
// is waiting for, and what it brings is the later look at the key.
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { vi } from "../i18n/vi";
import type { FakeBackend } from "../test/fake-backend";
import { holdEach, mountStore, shownKeys, storeBackend, takeOut } from "../test/script-store-screen";

const { scriptStore: words } = vi;

const T1 = "2026-10-12T01:00:00+00:00";
const T2 = "2026-10-12T02:00:00+00:00";
/** Ten characters and twenty-five: each a JSON text, so each is set out as it is. */
const FIRST = "1234567890";
const SECOND = "1234567890123456789012345";
const REFUSED = "Kho đang bận, thử lại sau.";

let backend: FakeBackend;
/** One per value read asked for, in the order asked: calling it lets that answer land. */
let land: Array<() => void>;

beforeEach(() => {
  backend = storeBackend();
  backend.scriptStore.keepText("coach", "job:brief", "seen", FIRST, T1).keepText("coach", "job:brief", "tail", "0", T1);
});

const view = () => screen.findByRole("button", { name: words.viewLabel("seen") });
const hide = () => screen.findByRole("button", { name: words.hideLabel("seen") });
const row = () => within(screen.getAllByTestId("script-store-entry")[0]);
const boxText = () => screen.queryByTestId("script-store-value")?.textContent ?? null;
const lands = (at: number) => act(async () => land[at]());
/** Lets every answer already on its way land. */
const settled = () => act(async () => new Promise<void>((resolve) => setTimeout(resolve, 0)));

/** View, hide, view: two reads of the key under way, with `between` done to the server
 *  after the first was answered and before the second was asked. */
async function askedTwice(between: () => void, before: () => void = () => {}) {
  mountStore(backend);
  const press = await view();
  land = holdEach(backend, /\/value\?/);
  before();
  await userEvent.click(press);
  await userEvent.click(await hide());
  between();
  await userEvent.click(await view());
  expect(land).toHaveLength(2);
  expect(row().getByText(words.valueLoading)).toBeInTheDocument();
}

const writtenAgain = () => backend.scriptStore.keepText("coach", "job:brief", "seen", SECOND, T2);

describe("two reads of one key's value under way at once", () => {
  it("leaves the box waiting when the earlier one lands first, and fills it with the later one", async () => {
    await askedTwice(writtenAgain);

    await lands(0);
    await settled();

    expect(boxText()).toBeNull();
    expect(row().getByText(words.valueLoading)).toBeInTheDocument();

    await lands(1);

    await waitFor(() => expect(boxText()).toBe(SECOND));
    await waitFor(() => expect(row().getByRole("time")).toHaveAttribute("datetime", T2));
    expect(boxText()).toBe(SECOND);
  });

  it("keeps the later one's value when the earlier one lands after it", async () => {
    await askedTwice(writtenAgain);

    await lands(1);
    await waitFor(() => expect(boxText()).toBe(SECOND));
    await lands(0);
    await settled();

    expect(boxText()).toBe(SECOND);
    await waitFor(() => expect(row().getByRole("time")).toHaveAttribute("datetime", T2));
    expect(boxText()).toBe(SECOND);
  });

  it("shows no refusal of the earlier one while the later one is waited for", async () => {
    const refuse = () => {
      backend.scriptStore.refuse.value = { status: 409, detail: REFUSED };
    };
    const allow = () => {
      backend.scriptStore.refuse.value = undefined;
    };
    await askedTwice(allow, refuse);

    await lands(0);
    await settled();

    expect(screen.queryByRole("alert")).toBeNull();
    expect(row().getByText(words.valueLoading)).toBeInTheDocument();

    await lands(1);

    await waitFor(() => expect(boxText()).toBe(FIRST));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the later one's refusal, not the earlier one's value", async () => {
    await askedTwice(() => {
      backend.scriptStore.refuse.value = { status: 409, detail: REFUSED };
    });

    await lands(0);
    await settled();
    expect(boxText()).toBeNull();
    await lands(1);

    expect(await screen.findByRole("alert")).toHaveTextContent(REFUSED);
    expect(boxText()).toBeNull();
  });

  it("does not take the key out for an earlier one that found it gone", async () => {
    // Gone when first asked for, kept again by a script before the second.
    await askedTwice(
      () => backend.scriptStore.keepText("coach", "job:brief", "seen", SECOND, T1),
      () => takeOut(backend, "coach", "job:brief", "seen"),
    );

    await lands(0);
    await settled();

    expect(shownKeys()).toEqual(["seen", "tail"]);
    expect(screen.getByRole("status")).toBeEmptyDOMElement();

    await lands(1);

    await waitFor(() => expect(boxText()).toBe(SECOND));
    expect(shownKeys()).toEqual(["seen", "tail"]);
  });

  it("takes the key out when the later one finds it gone, whatever the earlier one read", async () => {
    await askedTwice(() => takeOut(backend, "coach", "job:brief", "seen"));

    await lands(1);

    await waitFor(() => expect(shownKeys()).toEqual(["tail"]));
    expect(screen.getByRole("status")).toHaveTextContent(words.gone('"seen"'));
    await lands(0);
    await settled();
    expect(shownKeys()).toEqual(["tail"]);
    expect(boxText()).toBeNull();
  });

  it("fill nothing once the person has closed the box again", async () => {
    await askedTwice(writtenAgain);
    await userEvent.click(await hide());

    await lands(0);
    await lands(1);
    await settled();

    expect(boxText()).toBeNull();
    expect(row().queryByText(words.valueLoading)).toBeNull();
    expect(await view()).toHaveAttribute("aria-expanded", "false");
  });
});

describe("one read of a key's value, closed before it lands", () => {
  it("still takes the key out when the server says it is gone", async () => {
    mountStore(backend);
    const press = await view();
    land = holdEach(backend, /\/value\?/);
    takeOut(backend, "coach", "job:brief", "seen");
    await userEvent.click(press);
    await userEvent.click(await hide());

    await lands(0);

    await waitFor(() => expect(shownKeys()).toEqual(["tail"]));
    expect(screen.getByRole("status")).toHaveTextContent(words.gone('"seen"'));
  });
});
