/**
 * A name, renamed where it is shown: the conversation's, or a canvas's beside it.
 *
 * A modal prompt asks the person to retype a name they can already see, in a box that
 * hides the thread behind it. Clicking the title instead puts a field exactly where the
 * heading was: Enter keeps the new name, Escape abandons it, and clicking away keeps it
 * too, because someone who typed a name and looked elsewhere meant the name.
 */

import { useEffect, useRef, useState } from "react";
import { vi } from "../i18n/vi";

interface Props {
  title: string;
  onRename: (title: string) => void;
  /** A canvas names a part of the page, under the conversation's level-1 heading. */
  level?: 1 | 2;
  maxLength?: number;
  /** The field's name. */
  label?: string;
  /** The tooltip on the name. */
  hint?: string;
  /** What shows while the name is empty. */
  placeholder?: string;
  /** Opens with the field ready: something just made still has a placeholder name. */
  startEditing?: boolean;
}

export function EditableTitle({
  title,
  onRename,
  level = 1,
  maxLength = 120,
  label = vi.rename,
  hint = vi.renameHint,
  placeholder = vi.newConversation,
  startEditing = false,
}: Props) {
  const [editing, setEditing] = useState(startEditing);
  const [draft, setDraft] = useState(title);
  const input = useRef<HTMLInputElement>(null);

  // The name arrives selected, so typing replaces it instead of appending to it.
  useEffect(() => {
    if (!editing) return;
    input.current?.focus();
    input.current?.select();
  }, [editing]);

  // A name written in the background while the field is open does not disturb it: the
  // person typing is saying what the thread is called, and their draft is sent on commit
  // even though the heading behind them has changed in the meantime.
  const commit = () => {
    setEditing(false);
    const next = draft.trim();
    if (next && next !== title) onRename(next);
  };

  // The name stays a heading either way: it is what the page or its part is about, and
  // a control that opens an editor must not take that role away from it.
  const Heading = level === 2 ? "h2" : "h1";
  return (
    <Heading className="title-heading">
      {editing ? (
        <input
          ref={input}
          className="title-input"
          aria-label={label}
          value={draft}
          maxLength={maxLength}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
            // Escape leaves the name as it was; the draft is dropped, not saved.
            if (e.key === "Escape") setEditing(false);
          }}
        />
      ) : (
        <button
          type="button"
          className="editable-title"
          title={hint}
          onClick={() => {
            setDraft(title);
            setEditing(true);
          }}
        >
          {title || placeholder}
        </button>
      )}
    </Heading>
  );
}
