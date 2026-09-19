import { useEffect, useState, type KeyboardEvent } from "react";
import { vi } from "../i18n/vi";

interface Props {
  disabled: boolean;
  busy: boolean;
  draft?: string;
  onSend: (text: string) => void;
  onStop: () => void;
}

export function Composer({ disabled, busy, draft, onSend, onStop }: Props) {
  const [text, setText] = useState("");
  useEffect(() => {
    if (draft !== undefined) setText(draft);
  }, [draft]);

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled || busy) return;
    onSend(trimmed);
    setText("");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
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
      <textarea
        aria-label={vi.composerPlaceholder}
        placeholder={vi.composerPlaceholder}
        value={text}
        rows={2}
        disabled={disabled}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={onKeyDown}
      />
      {busy ? (
        <button type="button" className="danger" onClick={onStop}>
          {vi.stop}
        </button>
      ) : (
        <button type="submit" className="primary" disabled={disabled || !text.trim()}>
          {vi.send}
        </button>
      )}
    </form>
  );
}
