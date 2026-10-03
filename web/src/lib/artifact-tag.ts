/**
 * The tag that opens the result of every successful canvas write, and the ids it names. The
 * pattern is the server's (`my_agent_crew/artifacts/tag.py`): a result is a write when it starts
 * this way and for no other reason, so nothing else in a result, a canvas's own text least of
 * all, can make one.
 */

const TAG_RE = /^\[artifact ([0-9a-f]{12}) v(\d+)( unchanged)?\]/;
const ID_RE = /^[0-9a-f]{12}$/;

export type ArtifactTag = { id: string; version: number; unchanged: boolean };

/** The ids the server makes, the only ones worth asking it about: `..` and `../x` never form a URL. */
export function isArtifactId(id: string): boolean {
  return ID_RE.test(id);
}

/** What the tag at the start of a tool result says, or null when the result has none. */
export function parseArtifactTag(output: string | null): ArtifactTag | null {
  const found = output === null ? null : TAG_RE.exec(output);
  if (found === null) return null;
  const version = Number(found[2]);
  return Number.isSafeInteger(version) ? { id: found[1], version, unchanged: found[3] !== undefined } : null;
}
