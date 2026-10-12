import type { Conversation } from "../../api/types";
import { useCanvasAutoOpen } from "../../hooks/use-canvas-auto-open";
import { useCanvasDock } from "../../hooks/use-canvas-dock";
import { useCanvasFocus } from "../../hooks/use-canvas-focus";
import { useCanvasWriting } from "../../hooks/use-canvas-writing";
import { useLivePreview } from "../../hooks/use-live-preview";
import { useMediaQuery } from "../../hooks/use-media-query";
import { useSavingNote } from "../../hooks/use-saving-note";
import type { ChatProps } from "./chat-props";

// Wide enough to keep the conversation's activity open beside the chat. Matches the
// breakpoint in shell.css where the three-column layout folds back to two.
const DOCKED_ACTIVITY_QUERY = "(min-width: 1101px)";

interface CanvasParts extends Pick<ChatProps, "thread" | "activity"> {
  active: Conversation | null;
}

/** The canvas beside the chat: its dock, the one an agent is writing, and what opens one from a card. */
export function useChatCanvas({ thread, activity, active }: CanvasParts) {
  // Narrower than this, the activity is a strip under the thread and an open canvas covers
  // the chat column; wider, both share the column beside the chat.
  const wide = useMediaQuery(DOCKED_ACTIVITY_QUERY);
  const dock = useCanvasDock(active?.id ?? null, activity.state.connected, wide);
  const saving = useSavingNote();
  useCanvasFocus(active?.id ?? null, wide, dock);
  // A canvas the agent is still writing shows where the dock is without opening it, on a device
  // that has not turned that off. It comes first: the canvas it turns into is its to open, not
  // the hook's that opens what an agent made.
  const writing = useCanvasWriting(thread, dock, wide, useLivePreview().enabled);
  useCanvasAutoOpen(thread, dock, wide, writing.callId);
  const showing = writing.shown !== null;
  const { leave: leaveWriting } = writing;
  const { titleOf, isGone, verify } = dock.list;
  // Opening the canvas the dock already holds moves nothing, so a card pressed while a canvas
  // being written stands before it has to put that away itself.
  const openCanvas = (id: string) => {
    if (showing) leaveWriting();
    dock.open(id);
  };
  const canvasLinks = { titleOf, isGone, verify, open: openCanvas };
  return { wide, dock, saving, writing, showing, leaveWriting, canvasLinks };
}
