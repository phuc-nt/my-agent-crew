/**
 * What the canvases have to say in the chat, outside the dock: the saves left behind as the person
 * moved on that did not land, and that a message went before the canvas it names was saved.
 *
 * The second is said of the conversation the message went in, until the next message there goes
 * with its canvas saved or the person puts the line away.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { type HandoffFailure, onHandoffFailed } from "../lib/canvas-handoff";

export type CanvasChatNotices = {
  handoffs: HandoffFailure[];
  dismissHandoff(id: string): void;
  /** The last message of this conversation went while the canvas it names had text no version held. */
  sentUnsaved: boolean;
  /** Says so, or no longer, of the conversation that was open when this function was handed out. */
  noteSentUnsaved(on: boolean): void;
  /** Canvases closed anyway: the person already knows their last save did not land. */
  kept: { current: Set<string> };
};

export function useCanvasChatNotices(conversationId: string | null): CanvasChatNotices {
  const [handoffs, setHandoffs] = useState<HandoffFailure[]>([]);
  const [unsaved, setUnsaved] = useState<readonly string[]>([]);
  const kept = useRef(new Set<string>());

  useEffect(
    () =>
      onHandoffFailed((failure) => {
        if (kept.current.delete(failure.id)) return;
        setHandoffs((told) => [...told.filter((f) => f.id !== failure.id), failure]);
      }),
    [],
  );

  const dismissHandoff = useCallback((id: string) => setHandoffs((told) => told.filter((f) => f.id !== id)), []);
  const noteSentUnsaved = useCallback(
    (on: boolean) => {
      if (conversationId === null) return;
      setUnsaved((was) => [...was.filter((id) => id !== conversationId), ...(on ? [conversationId] : [])]);
    },
    [conversationId],
  );
  const sentUnsaved = conversationId !== null && unsaved.includes(conversationId);
  return { handoffs, dismissHandoff, sentUnsaved, noteSentUnsaved, kept };
}
