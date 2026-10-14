// Where a desktop frame's picture is, when what is on screen does not say it.
//
// A frame is named by a screenshot that saved it. Where none in reach does, the picture is in
// the tool's folder: in the workspace, or under the agent's first write path, which only the
// agent's row tells. A request that fails leaves no picture; the card or the row it sits in
// reads as it would without one, which is what a picture removed since reads as too.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { folderPath, savedInMessages } from "../lib/desktop-frame";

/** A frame's picture found for a request, keyed so a row that comes to ask of another frame
 *  never draws the last one's. */
interface Found<T> {
  key: string;
  value: T;
}

function useFound<T>(key: string | null, find: () => Promise<T>): T | null {
  const [found, setFound] = useState<Found<T> | null>(null);
  useEffect(() => {
    if (key === null) return;
    let live = true;
    find().then(
      (value) => {
        if (live) setFound({ key, value });
      },
      // A picture that cannot be placed is no picture: nothing else on the card waits on it.
      () => undefined,
    );
    return () => {
      live = false;
    };
    // `find` is a fresh closure each render; the key names everything it reads.
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return found !== null && found.key === key ? found.value : null;
}

/** The picture of `frame` in the agent's folder, or null until its row is read. Nothing is
 *  asked while `frame` is null. */
export function useFolderPath(agentId: string | undefined, frame: string | null): string | null {
  const key = agentId && frame ? `${agentId}\n${frame}` : null;
  return useFound(key, async () => folderPath(frame as string, (await api.getAgent(agentId as string)).write_paths));
}

/** The frame a waiting action names, as the conversation tells of it. */
export interface FramePicture {
  agentId: string;
  path: string;
  /** When the screenshot that saved it ran; null when no screenshot of the conversation did. */
  takenAt: string | null;
}

/**
 * The picture of `frame` for a call waiting in a conversation: the screenshot of the
 * conversation that saved that frame, else the agent's folder. Nothing is asked while `frame`
 * is null.
 */
export function useApprovalFrame(conversationId: string | undefined, frame: string | null): FramePicture | null {
  const key = conversationId && frame ? `${conversationId}\n${frame}` : null;
  return useFound(key, async () => {
    const detail = await api.getConversation(conversationId as string);
    const saved = savedInMessages(detail.messages, frame as string);
    if (saved) return { agentId: detail.agent_id, path: saved.path, takenAt: saved.at };
    const agent = await api.getAgent(detail.agent_id);
    return { agentId: detail.agent_id, path: folderPath(frame as string, agent.write_paths), takenAt: null };
  });
}
