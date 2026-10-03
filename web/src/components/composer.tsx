import { useEffect, useLayoutEffect, useRef, type KeyboardEvent } from "react";
import type { CommandInfo } from "../api/types";
import { useDraft } from "../hooks/use-draft";
import { useSendLock, type SendWords } from "../hooks/use-send-lock";
import { vi } from "../i18n/vi";
import { steerHint } from "../lib/steer-hint";
import { SlashPopover, useSlashMenu } from "./slash-popover";
import { Icon } from "./ui/icon";

/** Text handed back to the box from outside — Stop returning a chip's words, in order.
 *  `nonce` is what the box watches: the same text restored twice in a row (Stop pressed
 *  again with nothing new cleared) would not otherwise be a new value to react to. */
export interface RestoreRequest {
  nonce: number;
  text: string;
}

interface Props {
  disabled: boolean;
  /** The agent is busy somewhere — this tab's own turn, or one running elsewhere. The box
   *  is never locked for it; it only changes what the send button says and whether Stop
   *  is offered beside it. */
  busy: boolean;
  draft?: string;
  /** Where the unsent text is kept, one per conversation; absent keeps it in memory only. */
  draftKey?: string;
  /** Who the message goes to, so the empty box says so. */
  agentName?: string;
  /** The agent's own commands, offered when the message starts with "/". */
  commands?: CommandInfo[];
  /** Whether Stop should be offered while busy. Defaults to `busy`, so a caller that only
   *  ever passes `busy` keeps seeing Stop exactly as before this prop existed. A run this
   *  tab cannot touch — another channel's — passes `false` here instead. */
  stoppable?: boolean;
  /** Text to put back in the box from outside, oldest first, ahead of whatever is already
   *  being typed. */
  restore?: RestoreRequest | null;
  /** Why the box is waiting, said under it; absent says nothing. */
  note?: string;
  /** Takes the words. A promise keeps the box read-only, its text in place, until it settles:
   *  `true` spends the words and `false` leaves them where they were typed. Anything else
   *  spends them at once. */
  onSend: SendWords;
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
  stoppable = busy,
  restore,
  note,
  onSend,
  onStop,
}: Props) {
  const [text, setText] = useDraft(draftKey ?? null);
  const lock = useSendLock(draftKey ?? null, text, setText);
  const box = useRef<HTMLTextAreaElement>(null);
  const menu = useSlashMenu(commands, text, setText, box, disabled || lock.locked);
  const listed = menu.open && menu.shown.length > 0;
  // What a busy send will actually do to this text: the server alone decides for real
  // (`steer_text`, `find_command`), so a stale or unloaded command list only gets the
  // button's own wording wrong, never the send itself.
  const sendLabel = steerHint(text, commands) === "steer" ? vi.sendSteer : vi.sendQueue;
  // Keyed on the suggestion alone: re-running when the conversation changes would copy a
  // suggestion picked in one conversation over the draft kept for the next.
  useEffect(() => {
    if (draft !== undefined) setText(draft);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);

  // A chip's words coming back from Stop go ahead of whatever is already half-written,
  // never over it: the person may have kept typing while Stop was in flight. `setText`
  // only ever takes a plain string, so the join reads `text` as it stands this render
  // rather than through a functional update `useDraft` does not offer.
  const restoredNonce = useRef<number | null>(null);
  useEffect(() => {
    if (!restore || restore.nonce === restoredNonce.current) return;
    restoredNonce.current = restore.nonce;
    setText(text ? `${restore.text}\n\n${text}` : restore.text);
    box.current?.focus();
    // Only a new `nonce` should ever re-run this: `text` and `setText` change on every
    // keystroke, which would replay the same restore on top of what was typed since.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [restore]);

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
    if (!disabled) lock.send(onSend, text);
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
          readOnly={lock.locked}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={onKeyDown}
          onFocus={menu.onFocus}
          onBlur={menu.onBlur}
        />
        {commands.length > 0 && (
          <button
            type="button"
            className="composer-action slash"
            aria-label={vi.slash.open}
            title={vi.slash.open}
            aria-haspopup="listbox"
            aria-expanded={menu.open}
            disabled={disabled || lock.locked}
            // Keeps the focus, and with it the phone's keyboard, in the box.
            onMouseDown={(event) => event.preventDefault()}
            onClick={menu.toggle}
          >
            /
          </button>
        )}
        {busy && stoppable && (
          <button
            type="button"
            className="composer-action stop"
            aria-label={vi.stop}
            title={vi.stop}
            onClick={onStop}
          >
            <Icon name="stop" />
          </button>
        )}
        {/* Busy with nothing typed offers only Stop: a send button with nothing to send
            would just repeat it, and the two side by side at that point read as one
            choice offered twice. */}
        {(!busy || text.trim()) && (
          <button
            type="submit"
            className="composer-action primary"
            aria-label={busy ? sendLabel : vi.send}
            title={busy ? sendLabel : vi.send}
            disabled={disabled || !text.trim()}
          >
            <Icon name="arrow-up" />
          </button>
        )}
      </div>
      {note && (
        <p className="composer-note" role="status">
          {note}
        </p>
      )}
    </form>
  );
}
