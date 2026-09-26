import { useEffect, useId, useState, type KeyboardEvent, type RefObject } from "react";
import type { CommandInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { filterCommands, insertCommand, slashQuery } from "../lib/slash-filter";

export interface SlashMenu {
  open: boolean;
  shown: CommandInfo[];
  active: number;
  listId: string;
  optionId: (index: number) => string;
  pick: (command: CommandInfo) => void;
  /** Opens the list from the '/' button, or closes it when it is already open. */
  toggle: () => void;
  /** True when the key belonged to the list, so the composer must not also act on it. */
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>, composing: boolean) => boolean;
}

/** What the person asked of the list for the text on screen: shut it, or browse it over that text. */
type Hold = { text: string; kind: "closed" | "browsing" };

/**
 * The composer's command list: open while the box holds "/" and a name being typed, or
 * when the '/' button asked for it over text already written.
 *
 * Esc and the button answer the text they were made on. The next keystroke is a new
 * question, so the hold is dropped as soon as the text changes and the list answers again.
 */
export function useSlashMenu(
  commands: CommandInfo[],
  text: string,
  setText: (text: string) => void,
  box: RefObject<HTMLTextAreaElement | null>,
  disabled = false,
): SlashMenu {
  const listId = useId();
  const [hold, setHold] = useState<Hold | null>(null);
  if (hold !== null && hold.text !== text) setHold(null);
  const held = hold?.text === text ? hold.kind : null;
  const query = slashQuery(text);
  // A disabled box (an approval waiting) takes no message, so it offers no command either.
  const open =
    commands.length > 0 && !disabled && held !== "closed" && (query !== null || held === "browsing");
  const shown = open ? filterCommands(commands, query ?? "") : [];
  // Each new list, and each narrower one, starts again from its best match.
  const listKey = open ? (query ?? "") : null;
  const [active, setActive] = useState(0);
  const [activeFor, setActiveFor] = useState(listKey);
  if (activeFor !== listKey) {
    setActiveFor(listKey);
    setActive(0);
  }
  const current = Math.min(active, Math.max(shown.length - 1, 0));

  const pick = (command: CommandInfo) => {
    setText(insertCommand(text, command.name, commands));
    setHold(null);
    box.current?.focus();
  };

  const toggle = () => {
    if (open) setHold({ text, kind: "closed" });
    else if (text.trim() === "") setText("/");
    else setHold({ text, kind: "browsing" });
    box.current?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>, composing: boolean) => {
    if (!open) return false;
    if (event.key === "Escape") {
      event.preventDefault();
      // The drawer and the activity strip listen for Esc too; this one only meant the list.
      event.stopPropagation();
      setHold({ text, kind: "closed" });
      return true;
    }
    if (shown.length === 0) return false;
    const step = event.key === "ArrowDown" ? 1 : event.key === "ArrowUp" ? -1 : 0;
    if (step !== 0) {
      event.preventDefault();
      setActive((current + step + shown.length) % shown.length);
      return true;
    }
    // Enter while an IME composes commits the word, not a command.
    const choose = (event.key === "Enter" && !composing) || event.key === "Tab";
    if (choose && !event.shiftKey) {
      event.preventDefault();
      pick(shown[current]);
      return true;
    }
    return false;
  };

  const optionId = (index: number) => `${listId}-option-${index}`;
  return { open, shown, active: current, listId, optionId, pick, toggle, onKeyDown };
}

/** The list itself, drawn above the composer box. */
export function SlashPopover({ menu }: { menu: SlashMenu }) {
  const activeId = menu.open ? menu.optionId(menu.active) : null;
  useEffect(() => {
    // jsdom has no scrollIntoView; a browser does.
    if (activeId) document.getElementById(activeId)?.scrollIntoView?.({ block: "nearest" });
  }, [activeId]);

  if (!menu.open) return null;
  return (
    <div className="slash-popover" data-testid="slash-popover">
      {menu.shown.length === 0 ? (
        <p className="slash-empty" role="status">
          {vi.slash.empty}
        </p>
      ) : (
        <ul id={menu.listId} role="listbox" aria-label={vi.slash.list}>
          {menu.shown.map((command, index) => (
            <li key={command.name} role="presentation">
              <button
                type="button"
                role="option"
                id={menu.optionId(index)}
                aria-selected={index === menu.active}
                tabIndex={-1}
                // Keeps the focus, and with it the phone's keyboard, in the composer.
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => menu.pick(command)}
              >
                <span className="slash-name">/{command.name}</span>
                {command.description && (
                  <span className="slash-description">{command.description}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="slash-hint" aria-hidden="true">
        {vi.slash.hint}
      </p>
    </div>
  );
}
