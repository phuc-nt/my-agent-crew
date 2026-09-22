import type { RefObject } from "react";
import type { Conversation } from "../api/types";
import { vi } from "../i18n/vi";

/**
 * Folds a Vietnamese string down to what someone types when they are in a hurry.
 *
 * `đ` is a letter in its own right, not a `d` wearing a mark, so decomposition leaves it
 * untouched and has to be replaced by hand — without that, typing "doc" never finds "đọc".
 */
export function fold(text: string): string {
  return text
    .toLowerCase()
    .replace(/đ/g, "d")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");
}

/** Conversations whose title or summary contains the query, accents optional. */
export function matching(conversations: Conversation[], query: string): Conversation[] {
  const needle = fold(query.trim());
  if (needle === "") return conversations;
  return conversations.filter((c) => fold(`${c.title ?? ""} ${c.summary ?? ""}`).includes(needle));
}

interface Props {
  value: string;
  onChange: (value: string) => void;
  /** Held by the shell so a keyboard shortcut can put the cursor here. */
  inputRef?: RefObject<HTMLInputElement | null>;
}

export function ConversationSearch({ value, onChange, inputRef }: Props) {
  return (
    <div className="conversation-search">
      <input
        ref={inputRef}
        type="search"
        aria-label={vi.searchConversations}
        placeholder={vi.searchConversations}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
