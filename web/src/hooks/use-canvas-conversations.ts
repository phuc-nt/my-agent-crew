import { useEffect, useRef, useState } from "react";
import { artifactApi } from "../api/artifact-client";
import { onArtifactEvent } from "../lib/artifact-events";

/**
 * The conversations a canvas is used in, as the server lists them, for the canvas's own page.
 *
 * Read when the canvas is named and again whenever the stream says it changed. None are named
 * until a read lands, after a read that failed, or once the canvas is deleted: a list that may no
 * longer be true is worse than none, since each name on it is a way out of the page.
 */
export function useCanvasConversations(id: string): string[] {
  const [found, setFound] = useState<{ of: string; ids: string[] }>({ of: id, ids: [] });
  // Counts the reads asked for; an answer is kept only while its read is still the newest.
  const ticket = useRef(0);

  useEffect(() => {
    const read = () => {
      const mine = ++ticket.current;
      const settle = (ids: string[]) => {
        if (mine === ticket.current) setFound({ of: id, ids });
      };
      artifactApi.get(id).then(
        (detail) => settle(detail.conversation_ids),
        () => settle([]),
      );
    };
    read();
    const stop = onArtifactEvent((event) => {
      if (event.artifact.id !== id) return;
      if (!("deleted" in event.artifact)) return read();
      // Nothing is left to ask about, and a read still out would answer about what is gone.
      ticket.current += 1;
      setFound({ of: id, ids: [] });
    });
    return () => {
      ticket.current += 1;
      stop();
    };
  }, [id]);

  return found.of === id ? found.ids : [];
}
