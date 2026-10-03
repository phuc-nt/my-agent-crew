import type { ArtifactDetail, ArtifactSummary, ArtifactVersionMeta } from "../api/artifact-types";
import type { CanvasDraft } from "../lib/canvas-draft";
import { type CanvasEffect, type CanvasInput, type CanvasState, openState, step } from "../lib/canvas-machine";

/**
 * Drives the canvas machine one input at a time, the way `CanvasRunner` does, so a test reads as
 * the order things happened in: what the person did, what the server answered, what the stream
 * said. Every helper describes canvas "a1".
 */

const AT = "2026-10-02T03:00:00+00:00";

export function summaryAt(version: number, overrides: Partial<ArtifactSummary> = {}): ArtifactSummary {
  return {
    id: "a1",
    title: "Ghi chú",
    kind: "markdown",
    language: "",
    agent_id: "",
    head_version: version,
    source: "user",
    created_at: AT,
    updated_at: AT,
    ...overrides,
  };
}

export function detailAt(version: number, content: string, overrides: Partial<ArtifactDetail> = {}): ArtifactDetail {
  return { ...summaryAt(version), head_author: "user", content, conversation_ids: [], ...overrides };
}

export function metaAt(version: number, overrides: Partial<ArtifactVersionMeta> = {}): ArtifactVersionMeta {
  return {
    artifact_id: "a1",
    version,
    size: 0,
    author: "user",
    conversation_id: "",
    note: "",
    created_at: AT,
    updated_at: AT,
    ...overrides,
  };
}

export type Driver = { readonly state: CanvasState; send(input: CanvasInput): CanvasEffect[] };

export function drive(state: CanvasState): Driver {
  let current = state;
  return {
    get state() {
      return current;
    },
    send(input) {
      const out = step(current, input);
      current = out.state;
      return out.effects;
    },
  };
}

/** Canvas "a1" opened on `content` at `version`, as its first read leaves it. */
export function openOn(
  content: string,
  version = 5,
  options: { author?: string; draft?: CanvasDraft | null; kind?: string } = {},
): Driver {
  const canvas = drive(openState("a1", options.draft ?? null));
  const kind = options.kind ?? "markdown";
  canvas.send({ type: "read", detail: detailAt(version, content, { head_author: options.author ?? "user", kind }) });
  return canvas;
}

/** Types `text` into the canvas and lets the autosave timer fire; returns what that caused. */
export function typeAndPause(canvas: Driver, text: string): CanvasEffect[] {
  canvas.send({ type: "edit", text });
  return canvas.send({ type: "saveDue", reason: "timer" });
}

export const putsIn = (effects: CanvasEffect[]) =>
  effects.filter((effect): effect is Extract<CanvasEffect, { type: "put" }> => effect.type === "put");

export const getsIn = (effects: CanvasEffect[]) => effects.filter((effect) => effect.type === "get").length;

export const settledIn = (effects: CanvasEffect[]) =>
  effects.filter((effect): effect is Extract<CanvasEffect, { type: "settle" }> => effect.type === "settle");

/** A 409 as the server sends it: the newest version, its text and who wrote it. */
export function conflictAt(version: number, content: string, author = "agent:ming"): CanvasInput {
  return { type: "saveFailed", status: 409, conflict: { head_version: version, content, author }, full: null };
}

/** A save the network lost: no reply, so nobody knows whether it landed. */
export const lost: CanvasInput = { type: "saveFailed", status: null, conflict: null, full: null };
