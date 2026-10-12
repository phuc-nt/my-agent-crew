import { useCallback, useEffect, useState, type RefObject } from "react";
import type { Conversation } from "../../api/types";
import { useFork } from "../../hooks/use-fork";
import type { ThreadItem, ThreadState } from "../../state/thread-reducer";
import type { ChatProps } from "./chat-props";

interface ForkParts extends Pick<ChatProps, "list" | "onSelectConversation"> {
  state: ThreadState;
  active: Conversation | null;
  mainRef: RefObject<HTMLElement | null>;
}

/** The fork at a saved message, and the keyboard's way to the composer once it has opened. */
export function useChatFork({ list, onSelectConversation, state, active, mainRef }: ForkParts) {
  // Rewinds and forks the conversation at a saved user message. The list is refreshed and
  // the fork selected inside the hook itself; this screen only has to move focus into the
  // composer afterwards, the same way a cap raise does — the fork's own draft is already
  // seeded by the time `onSelectConversation` switches `draftKey` onto it.
  const { refresh: listRefresh } = list;
  const fork = useFork({ activeId: list.activeId, refresh: listRefresh, onSelectConversation });
  const [afterFork, setAfterFork] = useState(0);
  const { items: threadItems } = state;
  const onFork = useCallback(
    (item: ThreadItem) => {
      if (!active) return;
      void fork.fork(active.id, item, threadItems).then((ok) => {
        if (ok) setAfterFork((n) => n + 1);
      });
    },
    [active, fork, threadItems],
  );
  useEffect(() => {
    if (afterFork === 0) return;
    mainRef.current?.querySelector<HTMLElement>(".composer textarea:not(:disabled)")?.focus();
  }, [afterFork]);
  return { fork, onFork };
}
