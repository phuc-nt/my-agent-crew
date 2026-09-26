import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi as vitest } from "vitest";
import type { CommandInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { Composer } from "./composer";

const commands: CommandInfo[] = [
  { name: "plan", description: "Lập kế hoạch cho một việc", path: "/kit/commands/plan.md" },
  { name: "review", description: "Soát lại thay đổi", path: "/kit/commands/review.md" },
  { name: "ak:plan", description: "", path: "/kit/commands/ak/plan.md" },
];

function composer(extra: { commands?: CommandInfo[]; onSend?: (text: string) => void; disabled?: boolean; draft?: string } = {}) {
  render(
    <Composer
      disabled={extra.disabled ?? false}
      busy={false}
      draft={extra.draft}
      commands={extra.commands ?? commands}
      onSend={extra.onSend ?? (() => undefined)}
      onStop={() => undefined}
    />,
  );
  return screen.getByRole("textbox", { name: vi.composerPlaceholder });
}

const options = () => screen.queryAllByRole("option").map((o) => o.querySelector(".slash-name")?.textContent);
const selected = () => screen.getByRole("option", { selected: true }).querySelector(".slash-name")?.textContent;

describe("the command list in the composer", () => {
  it("opens on '/' as the first character with each command and its description", async () => {
    const box = composer();
    await userEvent.type(box, "/");

    const list = screen.getByRole("listbox", { name: vi.slash.list });
    expect(options()).toEqual(["/plan", "/review", "/ak:plan"]);
    expect(within(list).getByText("Lập kế hoạch cho một việc")).toBeInTheDocument();
    // The box points at the option Enter would take, so a screen reader follows the arrows.
    expect(box).toHaveAttribute("aria-controls", list.id);
    expect(box).toHaveAttribute("aria-activedescendant", screen.getByRole("option", { selected: true }).id);
  });

  it("narrows by name prefix first, then by what a name merely contains", async () => {
    const box = composer();
    await userEvent.type(box, "/pl");
    expect(options()).toEqual(["/plan", "/ak:plan"]);

    await userEvent.type(box, "x");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent(vi.slash.empty);
  });

  it("does not open for a '/' in the middle of the text", async () => {
    const box = composer();
    await userEvent.type(box, "đi /home");
    expect(screen.queryByTestId("slash-popover")).toBeNull();
    expect(box).not.toHaveAttribute("aria-controls");
  });

  it("moves with the arrows, wraps at the ends, and Enter inserts '/name ' and closes", async () => {
    const onSend = vitest.fn();
    const box = composer({ onSend });
    await userEvent.type(box, "/");
    expect(selected()).toBe("/plan");
    await userEvent.keyboard("{ArrowDown}");
    expect(selected()).toBe("/review");
    await userEvent.keyboard("{ArrowUp}{ArrowUp}");
    expect(selected()).toBe("/ak:plan");
    await userEvent.keyboard("{ArrowDown}{ArrowDown}{Enter}");

    expect(box).toHaveValue("/review ");
    expect(screen.queryByTestId("slash-popover")).toBeNull();
    // Picking is not sending: the next Enter sends the command as the server expands it.
    expect(onSend).not.toHaveBeenCalled();
    await userEvent.keyboard("{Enter}");
    expect(onSend).toHaveBeenCalledWith("/review");
  });

  it("inserts with Tab as well", async () => {
    const box = composer();
    await userEvent.type(box, "/re");
    await userEvent.keyboard("{Tab}");
    expect(box).toHaveValue("/review ");
    expect(box).toHaveFocus();
  });

  it("closes on Esc without inserting, keeps the Esc to itself, and the next key reopens it", async () => {
    const onDocumentKey = vitest.fn();
    document.addEventListener("keydown", onDocumentKey);
    try {
      const box = composer();
      await userEvent.type(box, "/re");
      await userEvent.keyboard("{Escape}");

      expect(screen.queryByTestId("slash-popover")).toBeNull();
      expect(box).toHaveValue("/re");
      // The drawer closes on Esc; that must not happen when the Esc only meant the list.
      expect(onDocumentKey).not.toHaveBeenCalledWith(expect.objectContaining({ key: "Escape" }));

      await userEvent.type(box, "v");
      expect(options()).toEqual(["/review"]);
      // Back to the very text it was closed on is still a new keystroke, not the old Esc.
      await userEvent.type(box, "{Backspace}");
      expect(box).toHaveValue("/re");
      expect(options()).toEqual(["/review"]);
    } finally {
      document.removeEventListener("keydown", onDocumentKey);
    }
  });

  it("sends a '/' text no command matches as it was written", async () => {
    const onSend = vitest.fn();
    const box = composer({ onSend });
    await userEvent.type(box, "/tmp{Enter}");
    expect(onSend).toHaveBeenCalledWith("/tmp");
  });
});

describe("the '/' button beside send, for touch", () => {
  it("opens the whole list on an empty box, and a tap inserts the command", () => {
    const box = composer();
    const button = screen.getByRole("button", { name: vi.slash.open });
    fireEvent.click(button);

    expect(box).toHaveValue("/");
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(options()).toEqual(["/plan", "/review", "/ak:plan"]);

    fireEvent.click(screen.getByRole("option", { name: /\/review/ }));
    expect(box).toHaveValue("/review ");
    expect(box).toHaveFocus();
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("closes the list when pressed again", async () => {
    const box = composer();
    await userEvent.type(box, "/");
    fireEvent.click(screen.getByRole("button", { name: vi.slash.open }));
    expect(screen.queryByTestId("slash-popover")).toBeNull();
    expect(box).toHaveValue("/");
  });

  it("offered over text already written, makes that text the command's arguments", async () => {
    const box = composer();
    await userEvent.type(box, "src/app.tsx");
    fireEvent.click(screen.getByRole("button", { name: vi.slash.open }));
    fireEvent.click(screen.getByRole("option", { name: /\/review/ }));
    expect(box).toHaveValue("/review src/app.tsx");
  });
});

describe("an agent without commands", () => {
  it("shows no '/' button and no list", async () => {
    const box = composer({ commands: [] });
    expect(screen.queryByRole("button", { name: vi.slash.open })).toBeNull();
    await userEvent.type(box, "/");
    expect(screen.queryByTestId("slash-popover")).toBeNull();
    expect(box).not.toHaveAttribute("aria-autocomplete");
  });
});

describe("a composer that takes no message", () => {
  it("offers no commands while an approval waits, even over a '/' already in the box", () => {
    composer({ disabled: true, draft: "/re" });
    expect(screen.getByRole("textbox")).toHaveValue("/re");
    expect(screen.queryByTestId("slash-popover")).toBeNull();
    expect(screen.getByRole("button", { name: vi.slash.open })).toBeDisabled();
  });
});
