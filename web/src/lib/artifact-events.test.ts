import { describe, expect, it } from "vitest";
import type { ArtifactEvent } from "../api/artifact-types";
import { emitArtifactEvent, onArtifactEvent } from "./artifact-events";

const event = (id: string): ArtifactEvent => ({ type: "artifact", artifact: { id, deleted: true }, conversation_ids: [] });

describe("artifact events", () => {
  it("hands each event to every listener until it unsubscribes", () => {
    const first: string[] = [];
    const second: string[] = [];
    const offFirst = onArtifactEvent((e) => first.push(e.artifact.id));
    const offSecond = onArtifactEvent((e) => second.push(e.artifact.id));
    emitArtifactEvent(event("x"));
    offFirst();
    emitArtifactEvent(event("y"));
    offSecond();
    emitArtifactEvent(event("z"));
    expect(first).toEqual(["x"]);
    expect(second).toEqual(["x", "y"]);
  });

  it("keeps the second subscription of a function when the first is removed", () => {
    const seen: string[] = [];
    const listener = (e: ArtifactEvent) => seen.push(e.artifact.id);
    const offFirst = onArtifactEvent(listener);
    const offSecond = onArtifactEvent(listener);
    emitArtifactEvent(event("x"));
    offFirst();
    offFirst();
    emitArtifactEvent(event("y"));
    offSecond();
    emitArtifactEvent(event("z"));
    expect(seen).toEqual(["x", "x", "y"]);
  });

  it("skips a listener removed during an event, and starts one added during it from the next", () => {
    const seen: string[] = [];
    let offLate = () => {};
    let offRemoved = () => {};
    const offFirst = onArtifactEvent((e) => {
      seen.push(`first:${e.artifact.id}`);
      offRemoved();
      if (e.artifact.id === "x") offLate = onArtifactEvent((later) => seen.push(`late:${later.artifact.id}`));
    });
    offRemoved = onArtifactEvent((e) => seen.push(`removed:${e.artifact.id}`));
    emitArtifactEvent(event("x"));
    emitArtifactEvent(event("y"));
    offFirst();
    offLate();
    expect(seen).toEqual(["first:x", "first:y", "late:y"]);
  });
});
