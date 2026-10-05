/**
 * A `FILE:` or `MEDIA:` line of a reply whose path names a canvas, not a file of the workspace.
 *
 * The server reads such a line by `artifact_ref` (`my_agent_crew/reply_attachments.py`) and sends
 * the canvas to the chat; the thread reads it by the same rule and draws the canvas. The Python
 * tests read the prefix from this file too, so it stays a one-line constant.
 */

import { isArtifactId } from "./artifact-tag";

export const ARTIFACT_REF = "artifact:";

/**
 * The canvas a path names: its id, "" for a path that sets out to name a canvas and names none
 * the server could have made, and null for the path of a file.
 */
export function artifactRef(path: string): string | null {
  if (!path.startsWith(ARTIFACT_REF)) return null;
  const id = path.slice(ARTIFACT_REF.length).trim();
  return isArtifactId(id) ? id : "";
}
