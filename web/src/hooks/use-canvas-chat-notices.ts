/**
 * What the canvases have to say in the chat, outside the dock: the saves left behind as the person
 * moved on that did not land, and that a message went before the canvas it names was saved.
 *
 * The first is said of a canvas until the person puts the line away or a later save leaves that
 * canvas with nothing unsaved.
 * The second is said of the conversation the message went in, until the next message there goes
 * with its canvas saved or the person puts the line away.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { type HandoffFailure, onCanvasSaved, onHandoffFailed } from "../lib/canvas-handoff";

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

  // A save lands with every pause in typing: the list is a new one only when it loses a line.
  const dismissHandoff = useCallback(
    (id: string) => setHandoffs((told) => (told.some((f) => f.id === id) ? told.filter((f) => f.id !== id) : told)),
    [],
  );
  useEffect(() => onCanvasSaved(dismissHandoff), [dismissHandoff]);
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
