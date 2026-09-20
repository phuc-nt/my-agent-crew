/**
 * Which lines a proposed memory write would add.
 *
 * An agent's memory proposal only ever appends, so the interesting question is not
 * "what changed" but "what is new" — a set difference on trimmed lines answers it
 * without pulling in a diff library for one panel.
 */

export type DiffLine = { text: string; added: boolean };

export function addedLines(current: string, proposed: string): DiffLine[] {
  const seen = new Set(splitLines(current));
  return splitLines(proposed).map((text) => ({ text, added: !seen.has(text) }));
}

function splitLines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
}
