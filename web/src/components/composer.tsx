import { useEffect, useLayoutEffect, useRef, type KeyboardEvent } from "react";
import type { CommandInfo } from "../api/types";
import { useDraft } from "../hooks/use-draft";
import { vi } from "../i18n/vi";
import { SlashPopover, useSlashMenu } from "./slash-popover";
import { Icon } from "./ui/icon";

interface Props {
  disabled: boolean;
  busy: boolean;
  draft?: string;
  /** Where the unsent text is kept, one per conversation; absent keeps it in memory only. */
  draftKey?: string;
  /** Who the message goes to, so the empty box says so. */
  agentName?: string;
  /** The agent's own commands, offered when the message starts with "/". */
  commands?: CommandInfo[];
  onSend: (text: string) => void;
  onStop: () => void;
}

/** The box grows with what is typed up to this many pixels, then scrolls. */
const MAX_HEIGHT = 240;

export function Composer({
  disabled,
  busy,
  draft,
  draftKey,
  agentName,
  commands = [],
  onSend,
  onStop,
}: Props) {
  const [text, setText] = useDraft(draftKey ?? null);
  const box = useRef<HTMLTextAreaElement>(null);
  const menu = useSlashMenu(commands, text, setText, box, disabled);
  const listed = menu.open && menu.shown.length > 0;
  // Keyed on the suggestion alone: re-running when the conversation changes would copy a
  // suggestion picked in one conversation over the draft kept for the next.
  useEffect(() => {
    if (draft !== undefined) setText(draft);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);

  // One line when empty, as tall as the message while it is written: a fixed two-row box
  // either wastes a line on every short message or hides the start of a long one. Empty,
  // the box keeps its one row: measuring then would size it to the placeholder, which
  // wraps on a phone and would leave a second, blank line once a short name replaces it.
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "";
    if (text) el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
  }, [text]);

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled || busy) return;
    onSend(trimmed);
    setText("");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // A composition in progress (Vietnamese Telex, Japanese IME) uses Enter to commit the
    // word; sending on that Enter would post half a word. Safari ends the composition
    // before the Enter that commits it arrives, so there `isComposing` is already false
    // and only the IME's keyCode 229 gives that Enter away.
    const composing = event.nativeEvent.isComposing || event.keyCode === 229;
    if (menu.onKeyDown(event, composing)) return;
    if (event.key === "Enter" && !event.shiftKey && !composing) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <form
      className="composer"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <div className={`composer-box${disabled ? " disabled" : ""}`}>
        <SlashPopover menu={menu} />
        <textarea
          ref={box}
          aria-label={vi.composerPlaceholder}
          aria-autocomplete={commands.length > 0 ? "list" : undefined}
          aria-controls={listed ? menu.listId : undefined}
          aria-activedescendant={listed ? menu.optionId(menu.active) : undefined}
          placeholder={agentName ? vi.composerPlaceholderFor(agentName) : vi.composerPlaceholder}
          value={text}
          rows={1}
          disabled={disabled}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={onKeyDown}
        />
        {commands.length > 0 && (
          <button
            type="button"
            className="composer-action slash"
            aria-label={vi.slash.open}
            title={vi.slash.open}
            aria-haspopup="listbox"
            aria-expanded={menu.open}
            disabled={disabled}
            // Keeps the focus, and with it the phone's keyboard, in the box.
            onMouseDown={(event) => event.preventDefault()}
            onClick={menu.toggle}
          >
            /
          </button>
        )}
        {busy ? (
          <button
            type="button"
            className="composer-action stop"
            aria-label={vi.stop}
            title={vi.stop}
            onClick={onStop}
          >
            <Icon name="stop" />
          </button>
        ) : (
          <button
            type="submit"
            className="composer-action primary"
            aria-label={vi.send}
            title={vi.send}
            disabled={disabled || !text.trim()}
          >
            <Icon name="arrow-up" />
          </button>
        )}
      </div>
    </form>
  );
}
