import type { Dispatch, SetStateAction } from "react";
import type { MessageCanvas } from "../../api/artifact-types";
import type { CanvasDock } from "../../hooks/use-canvas-dock";
import type { useSavingNote } from "../../hooks/use-saving-note";
import { vi } from "../../i18n/vi";
import type { SendResult } from "../../lib/send-result";
import type { ChatProps } from "./chat-props";
import type { useQueuedSend } from "./use-queued-send";

interface SendParts extends ReturnType<typeof useQueuedSend> {
  list: ChatProps["list"];
  create: ChatProps["list"]["create"];
  setQueued: Dispatch<SetStateAction<{ id: string; text: string } | null>>;
  saving: ReturnType<typeof useSavingNote>;
  dock: CanvasDock;
}

/** The composer's way to send, made in each render from what that render holds. */
export function chatSend({ list, create, setQueued, saving, dock, activeRef, sendRef }: SendParts) {
  // The composer keeps the words until this answers. A conversation that does not exist yet is
  // made first, and the words wait for it to load; one that does waits for the open canvas's
  // last save and goes with the canvas as it stands by then, which the chat says when that is
  // not what the person sees. `false` means nothing was sent:
  // the conversation could not be made, the person went to another one before the save landed,
  // or the server turned the message down before it began.
  const send = async (text: string): Promise<boolean> => {
    const id = list.activeId;
    if (!id) {
      const created = await create();
      if (created) setQueued({ id: created.id, text });
      return Boolean(created);
    }
    const unsaved = await saving.during(dock.flushForMessage());
    if (activeRef.current !== id) return false;
    const result = await sendRef.current(text, dock.messageCanvas());
    if (result.status !== "failed") dock.noteSentUnsaved(unsaved);
    return result.status !== "failed";
  };
  return send;
}

interface AskParts extends ReturnType<typeof useQueuedSend> {
  list: ChatProps["list"];
  dock: CanvasDock;
  wide: boolean;
  closeDock: CanvasDock["close"];
}

/** The ask bar's way to send, made the same way. */
export function chatAsk({ list, dock, wide, closeDock, activeRef, sendRef }: AskParts) {
  // A question about a passage of the open canvas. The panel has saved the canvas and names the
  // version, so this only posts it, to the conversation the person pressed Send in. A canvas that
  // covers the chat is put away once the server has taken the question, so that the answer shows.
  const ask = async (canvas: MessageCanvas, question: string): Promise<SendResult> => {
    const id = list.activeId;
    if (activeRef.current !== id) return { status: "failed", error: vi.canvas.ask.elsewhere };
    const result = await sendRef.current(question, canvas);
    // It went with the canvas as the panel saved it: the message that went unsaved is no longer the last.
    if (result.status !== "failed") dock.noteSentUnsaved(false);
    // Only the conversation the question went to has an overlay to put away.
    if (!wide && result.status !== "failed" && activeRef.current === id) void closeDock();
    return result;
  };
  return ask;
}
