import { type FakeReply, ok, refused } from "./fake-canvas-faults";

/** Declared ahead of the routes that read an id, as on the server: "usage" is no canvas. */
export const USAGE_PATH = "/artifacts/usage";

type Sized = { summary: { id: string }; versions: { size: number }[] };

/** `GET /artifacts/usage`: what every version of each canvas holds, and the room they all share. */
export function usageReply(method: string, canvases: Iterable<Sized>, cap: number): FakeReply {
  if (method !== "GET") return refused(405, "Method Not Allowed");
  const by_artifact: Record<string, number> = {};
  for (const { summary, versions } of canvases) {
    by_artifact[summary.id] = versions.reduce((total, version) => total + version.size, 0);
  }
  const sizes = Object.values(by_artifact);
  return ok({ count: sizes.length, bytes: sizes.reduce((total, size) => total + size, 0), cap, by_artifact });
}
