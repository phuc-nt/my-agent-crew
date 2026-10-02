import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { CommandInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { memoryStorage } from "../test/memory-storage";
import { Composer, type RestoreRequest } from "./composer";

let store: Map<string, string>;

beforeEach(() => {
  store = memoryStorage();
});

afterEach(() => {
  vitest.restoreAllMocks();
  vitest.unstubAllGlobals();
});

const commands: CommandInfo[] = [{ name: "plan", description: "Lập kế hoạch", path: "/kit/commands/plan.md" }];

/** A send the test answers by hand, the way the server's first word would. */
function pending() {
  let resolveSend: (spent: boolean) => void = () => undefined;
  const onSend = vitest.fn((_text: string) => new Promise<boolean>((resolve) => (resolveSend = resolve)));
  return { onSend, answer: (spent: boolean) => act(async () => resolveSend(spent)) };
}

type Extra = { restore?: RestoreRequest; draft?: string; commands?: CommandInfo[] };

function composer(draftKey: string, onSend: (text: string) => Promise<boolean> | void, extra: Extra = {}) {
  return <Composer disabled={false} busy={false} draftKey={draftKey} onSend={onSend} onStop={() => undefined} {...extra} />;
}

const box = () => screen.getByRole("textbox", { name: vi.composerPlaceholder });
const draftOf = (key: string) => store.get(`composer-draft:${key}`);

describe("the composer while a send is on its way", () => {
  it("holds the text in a read-only box and sends it once, however it is asked again", async () => {
    const send = pending();
    render(composer("c1", send.onSend));
    await userEvent.type(box(), "gửi đi{Enter}");
    await userEvent.keyboard("{Enter}{Enter}");
    await userEvent.click(screen.getByRole("button", { name: vi.send }));

    expect(send.onSend).toHaveBeenCalledTimes(1);
    expect(send.onSend).toHaveBeenCalledWith("gửi đi");
    expect(box()).toHaveAttribute("readonly");
    expect(box()).toHaveValue("gửi đi");
    expect(draftOf("c1")).toBe("gửi đi");
  });

  it("empties the box and drops the kept draft once the words are spent", async () => {
    const send = pending();
    render(composer("c1", send.onSend));
    await userEvent.type(box(), "gửi đi{Enter}");

    await send.answer(true);

    expect(box()).toHaveValue("");
    expect(box()).not.toHaveAttribute("readonly");
    expect(store.size).toBe(0);
  });

  it("gives the box back with its text and draft when the words were not taken, and sends again", async () => {
    const send = pending();
    render(composer("c1", send.onSend));
    await userEvent.type(box(), "gửi đi{Enter}");

    await send.answer(false);

    expect(box()).toHaveValue("gửi đi");
    expect(box()).not.toHaveAttribute("readonly");
    expect(draftOf("c1")).toBe("gửi đi");
    await userEvent.keyboard("{Enter}");
    expect(send.onSend).toHaveBeenCalledTimes(2);
  });

  it("treats a send that rejects like one that was not taken, and says so on the console", async () => {
    const logged = vitest.spyOn(console, "error").mockImplementation(() => undefined);
    render(composer("c1", () => Promise.reject(new Error("boom"))));
    await userEvent.type(box(), "gửi đi{Enter}");

    await waitFor(() => expect(box()).not.toHaveAttribute("readonly"));
    expect(box()).toHaveValue("gửi đi");
    expect(draftOf("c1")).toBe("gửi đi");
    expect(logged).toHaveBeenCalledWith("the message could not be sent", expect.any(Error));
  });

  it("empties the box at once when the handler answers nothing", async () => {
    const onSend = vitest.fn();
    render(composer("c1", onSend));
    await userEvent.type(box(), "gửi đi{Enter}");

    expect(onSend).toHaveBeenCalledWith("gửi đi");
    expect(box()).toHaveValue("");
    expect(box()).not.toHaveAttribute("readonly");
    expect(store.size).toBe(0);
  });

  it("keeps the hold with the conversation the words were typed in", async () => {
    const send = pending();
    const view = render(composer("c1", send.onSend));
    await userEvent.type(box(), "gửi đi{Enter}");

    view.rerender(composer("c2", send.onSend));
    expect(box()).not.toHaveAttribute("readonly");
    expect(box()).toHaveValue("");
    await userEvent.type(box(), "việc khác");
    expect(box()).toHaveValue("việc khác");

    view.rerender(composer("c1", send.onSend));
    expect(box()).toHaveAttribute("readonly");
    expect(box()).toHaveValue("gửi đi");
  });

  it("drops the draft of the conversation left once its words are spent, and keeps the one the person is in", async () => {
    const send = pending();
    const view = render(composer("new", send.onSend));
    await userEvent.type(box(), "gửi đi{Enter}");
    view.rerender(composer("c9", send.onSend));
    await userEvent.type(box(), "việc khác");

    await send.answer(true);

    expect(box()).toHaveValue("việc khác");
    expect(draftOf("new")).toBeUndefined();
    expect(draftOf("c9")).toBe("việc khác");
  });

  it("keeps the draft of the conversation left when its words were not taken", async () => {
    const send = pending();
    const view = render(composer("c1", send.onSend));
    await userEvent.type(box(), "gửi đi{Enter}");
    view.rerender(composer("c2", send.onSend));

    await send.answer(false);

    expect(draftOf("c1")).toBe("gửi đi");
    view.rerender(composer("c1", send.onSend));
    expect(box()).toHaveValue("gửi đi");
    expect(box()).not.toHaveAttribute("readonly");
  });

  it("empties only what was sent when Stop handed queued words back during the wait", async () => {
    const send = pending();
    const view = render(composer("c1", send.onSend));
    await userEvent.type(box(), "gửi đi{Enter}");

    view.rerender(composer("c1", send.onSend, { restore: { nonce: 1, text: "chữ cũ" } }));
    expect(box()).toHaveValue("chữ cũ\n\ngửi đi");
    await send.answer(true);

    expect(box()).toHaveValue("chữ cũ");
    expect(draftOf("c1")).toBe("chữ cũ");
  });

  it("leaves a suggestion that replaced the text during the wait", async () => {
    const send = pending();
    const view = render(composer("c1", send.onSend));
    await userEvent.type(box(), "gửi đi{Enter}");

    view.rerender(composer("c1", send.onSend, { draft: "gợi ý" }));
    await send.answer(true);

    expect(box()).toHaveValue("gợi ý");
    expect(draftOf("c1")).toBe("gợi ý");
  });

  it("puts the command list away, and takes no command, while the box is held", async () => {
    const send = pending();
    render(composer("c1", send.onSend, { commands }));
    await userEvent.type(box(), "/pla");
    expect(screen.getByRole("listbox")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: vi.send }));
    expect(send.onSend).toHaveBeenCalledWith("/pla");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(screen.getByRole("button", { name: vi.slash.open })).toBeDisabled();

    await userEvent.keyboard("{Enter}");
    expect(box()).toHaveValue("/pla");
    expect(send.onSend).toHaveBeenCalledTimes(1);
  });
});
