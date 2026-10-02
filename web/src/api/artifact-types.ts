/**
 * Canvases as the REST routes and the activity stream describe them.
 *
 * Version numbers rise but have gaps: a person's autosaves within a burst fold into one version,
 * and the version folded away reads as gone. Nothing here assumes `head_version - 1` exists.
 */

/** A canvas without its text, as lists and events carry it. `agent_id` is "" when a person made it. */
export type ArtifactSummary = {
  id: string;
  title: string;
  kind: string;
  language: string;
  agent_id: string;
  head_version: number;
  source: string;
  created_at: string;
  updated_at: string;
};

/** A canvas with its newest version's text and author, and the conversations linked to it. */
export type ArtifactDetail = ArtifactSummary & {
  head_author: string;
  content: string;
  conversation_ids: string[];
};

/** A version without its text. `author` is "user" or "agent:<id>"; a restore's note is
 *  "restore:<n>", naming the version it brought back. */
export type ArtifactVersionMeta = {
  artifact_id: string;
  version: number;
  size: number;
  author: string;
  conversation_id: string;
  note: string;
  created_at: string;
  updated_at: string;
};

export type ArtifactVersion = ArtifactVersionMeta & { content: string };

/** What a person may create from the web; agents make the other kinds. */
export type NewArtifact = {
  title: string;
  kind: "markdown" | "code";
  content?: string;
  conversation_id?: string;
};

/** A 409's body: the newest version, which the refused save was not based on. */
export type ArtifactConflict = { head_version: number; content: string; author: string };

/** A 507's body: what every canvas holds together, the ceiling, and the largest canvases. */
export type StorageFull = {
  used: number;
  cap: number;
  largest: { id: string; title: string; size: number }[];
};

/** A passage selected in a canvas: the version it was read in, its text, and the lines it spans. */
export type FocusSelection = { version: number; text: string; line_start: number; line_end: number };

/** The canvas a conversation has open on the web, with the selected passage if there is one. */
export type CanvasFocus = { artifact_id: string; selection: FocusSelection | null };

/** The canvas open in the tab that sends a message, as the chat route takes it. A null
 *  `artifact_id` is a tab with none open; a message sent without the field says nothing. */
export type MessageCanvas = { artifact_id: string | null; selection?: FocusSelection | null };

/** A committed change, never with its text: the canvas's summary, or the id of a deleted one,
 *  with the conversations linked at that moment ("[]" for a canvas just created). */
export type ArtifactEvent = {
  type: "artifact";
  artifact: ArtifactSummary | { id: string; deleted: true };
  conversation_ids: string[];
};
