import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { vi } from "../i18n/vi";
import { Icon } from "./ui/icon";

interface Props {
  disabled: boolean;
  busy: boolean;
  draft?: string;
  /** Who the message goes to, so the empty box says so. */
  agentName?: string;
  onSend: (text: string) => void;
  onStop: () => void;
}

/** The box grows with what is typed up to this many pixels, then scrolls. */
const MAX_HEIGHT = 240;

export function Composer({ disabled, busy, draft, agentName, onSend, onStop }: Props) {
  const [text, setText] = useState("");
  const box = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (draft !== undefined) setText(draft);
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
    // word; sending on that Enter would post half a word.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
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
        <textarea
          ref={box}
          aria-label={vi.composerPlaceholder}
          placeholder={agentName ? vi.composerPlaceholderFor(agentName) : vi.composerPlaceholder}
          value={text}
          rows={1}
          disabled={disabled}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={onKeyDown}
        />
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
