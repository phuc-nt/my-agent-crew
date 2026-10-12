import { useCallback, useEffect, useRef, type Dispatch, type SetStateAction } from "react";
import type { ChatProps } from "./chat-props";

interface QueuedSendParts extends Pick<ChatProps, "list" | "thread"> {
  queued: { id: string; text: string } | null;
  setQueued: Dispatch<SetStateAction<{ id: string; text: string } | null>>;
  restoreText: (text: string) => void;
}

/** What a late send posts through, and the sending of words that waited for their conversation. */
export function useQueuedSend({ list, thread, queued, setQueued, restoreText }: QueuedSendParts) {
  const { send: threadSend, detail } = thread;
  // A send waits for the canvas to be saved before it posts. By then the person may be in
  // another conversation, and this one may have become busy: it posts through what is current.
  const activeRef = useRef(list.activeId);
  activeRef.current = list.activeId;
  const sendRef = useRef(threadSend);
  sendRef.current = threadSend;
  // Only a send the server never took gives its words back: one it queued is held there and
  // shown as a chip, and one it began a turn for is on screen as a message.
  const sendOrRestore = useCallback(
    async (text: string) => {
      const result = await threadSend(text);
      if (result.status === "failed") restoreText(text);
    },
    [threadSend, restoreText],
  );
  // A message typed before any conversation exists waits until the new one has loaded.
  useEffect(() => {
    if (queued && detail?.id === queued.id) {
      setQueued(null);
      void sendOrRestore(queued.text);
    }
  }, [queued, detail?.id, sendOrRestore]);
  return { activeRef, sendRef };
}
