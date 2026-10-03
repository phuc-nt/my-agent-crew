/**
 * The canvas routes. A refused request keeps the server's structured body in `ApiError.detail`;
 * the readers below give it a shape only when it has that shape, so a 409 or a 507 from anything
 * but the canvas store is never taken for one.
 */

import type {
  ArtifactConflict,
  ArtifactDetail,
  ArtifactSummary,
  ArtifactVersion,
  ArtifactVersionMeta,
  CanvasFocus,
  MessageCanvas,
  NewArtifact,
  StorageFull,
} from "./artifact-types";
import { ApiError, query, request } from "./client";

const artifactPath = (id: string) => `/artifacts/${encodeURIComponent(id)}`;
const focusPath = (conversationId: string) => `/conversations/${encodeURIComponent(conversationId)}/canvas`;

export type SaveOptions = { signal?: AbortSignal; keepalive?: boolean };

/** The body of a save, whose size a request kept alive past the page has to fit. */
export const saveBody = (content: string, baseVersion: number) =>
  JSON.stringify({ content, base_version: baseVersion });

export const artifactApi = {
  list: (conversationId?: string, q?: string) =>
    request<ArtifactSummary[]>(`/artifacts${query({ conversation_id: conversationId, q })}`),
  create: (body: NewArtifact) =>
    request<ArtifactDetail>("/artifacts", { method: "POST", body: JSON.stringify(body) }),
  get: (id: string, signal?: AbortSignal) => request<ArtifactDetail>(artifactPath(id), { signal }),
  /** `baseVersion` is the version the text was edited from. The reply's `version` is the base
   *  of the next save, whether the server folded this one into the save before it or not. */
  save: (id: string, content: string, baseVersion: number, options: SaveOptions = {}) =>
    request<ArtifactVersionMeta>(artifactPath(id), {
      method: "PUT",
      body: saveBody(content, baseVersion),
      signal: options.signal,
      keepalive: options.keepalive,
    }),
  rename: (id: string, title: string) =>
    request<ArtifactSummary>(artifactPath(id), { method: "PATCH", body: JSON.stringify({ title }) }),
  restore: (id: string, version: number) =>
    request<ArtifactVersionMeta>(`${artifactPath(id)}/restore`, {
      method: "POST",
      body: JSON.stringify({ version }),
    }),
  versions: (id: string) => request<ArtifactVersionMeta[]>(`${artifactPath(id)}/versions`),
  version: (id: string, version: number) =>
    request<ArtifactVersion>(`${artifactPath(id)}/versions/${version}`),
  rawUrl: (id: string, options: { version?: number; download?: boolean } = {}) =>
    `/api${artifactPath(id)}/raw${query({ version: options.version, download: options.download ? 1 : undefined })}`,
  /** The canvas a conversation has open, or null when none is. */
  getFocus: (conversationId: string) => request<CanvasFocus | null>(focusPath(conversationId)),
  /** What `getFocus` reads next: `artifact_id: null` closes the canvas. A canvas that is gone is a 404. */
  putFocus: (conversationId: string, body: MessageCanvas) =>
    request<CanvasFocus | null>(focusPath(conversationId), { method: "PUT", body: JSON.stringify(body) }),
};

function detailOf(error: unknown, status: number): Record<string, unknown> | null {
  if (!(error instanceof ApiError) || error.status !== status) return null;
  const detail = error.detail;
  return typeof detail === "object" && detail !== null && !Array.isArray(detail)
    ? (detail as Record<string, unknown>)
    : null;
}

/** The newest version a refused save was not based on. */
export function conflictOf(error: unknown): ArtifactConflict | null {
  const detail = detailOf(error, 409);
  if (!detail) return null;
  const { head_version, content, author } = detail;
  return typeof head_version === "number" && typeof content === "string" && typeof author === "string"
    ? { head_version, content, author }
    : null;
}

/** What a canvas was held to when the server refused it as too large, in bytes. */
export function sizeCapOf(error: unknown): number | null {
  const cap = detailOf(error, 413)?.cap;
  return typeof cap === "number" ? cap : null;
}

/** How full the canvas store is, and its largest canvases. */
export function storageFullOf(error: unknown): StorageFull | null {
  const detail = detailOf(error, 507);
  if (!detail) return null;
  const { used, cap, largest } = detail;
  if (typeof used !== "number" || typeof cap !== "number" || !Array.isArray(largest)) return null;
  const entries = largest as unknown[];
  return entries.every(isLargest) ? { used, cap, largest: entries } : null;
}

function isLargest(entry: unknown): entry is StorageFull["largest"][number] {
  if (typeof entry !== "object" || entry === null) return false;
  const { id, title, size } = entry as Record<string, unknown>;
  return typeof id === "string" && typeof title === "string" && typeof size === "number";
}

/** The newest version of a canvas whose asked-for version was folded away; null when the canvas
 *  itself is gone, or for any other error. */
export function versionGoneOf(error: unknown): number | null {
  const detail = detailOf(error, 404);
  return typeof detail?.head_version === "number" ? detail.head_version : null;
}
