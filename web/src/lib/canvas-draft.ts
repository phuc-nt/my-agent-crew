// A canvas's unsaved text, kept on this device so a reload, a closed tab or a lost connection
// does not lose what the person typed. The panel writes it shortly after each keystroke and at
// once when the page may go away; reopening the canvas finds it and merges it with the newest
// version (see canvas-machine.ts).
//
// A draft the browser refuses is held in this tab instead, and read back like a stored one: the
// text outlives its panel, though not the tab, so the page asks before it closes while one is held.
import { keys, readJson, readText, writeText } from "./local-store";
import { guardUnload } from "./unload-guard";

const PREFIX = "canvas-draft:";
/** Drafts kept at most; the ones saved longest ago go first. */
const KEEP = 10;
const MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;

/** The drafts only this tab holds, by canvas, and what makes the page ask while there is one. */
const tabOnly = new Map<string, CanvasDraft>();
let stopAsking: (() => void) | null = null;
/** The draft the quota refused last, by its `weight`: no lighter one has been written since. */
let refused: { id: string; weight: number } | null = null;

/**
 * The text and the version it was edited from. `sent` names, by `textKey`, the texts of saves
 * that were out or unanswered, so reopening on a version that holds one of them knows it for the
 * person's own. `saved_at` is milliseconds since the epoch.
 */
export type CanvasDraft = {
  artifact_id: string;
  base_version: number;
  base: string;
  text: string;
  saved_at: number;
  sent: string[];
};

function isDraft(value: unknown): value is CanvasDraft {
  if (typeof value !== "object" || value === null) return false;
  const { artifact_id, base_version, base, text, saved_at, sent } = value as Record<string, unknown>;
  return (
    typeof artifact_id === "string" &&
    Number.isInteger(base_version) &&
    (base_version as number) >= 1 &&
    typeof base === "string" &&
    typeof text === "string" &&
    typeof saved_at === "number" &&
    Array.isArray(sent) &&
    sent.every((key) => typeof key === "string")
  );
}

/**
 * A short name for `text`: its length and a 53-bit hash (cyrb53). A draft keeps these rather
 * than the texts, which could be half a megabyte each.
 */
export function textKey(text: string): string {
  let h1 = 0xdeadbeef;
  let h2 = 0x41c6ce57;
  for (let i = 0; i < text.length; i++) {
    const ch = text.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507);
  h1 ^= Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507);
  h2 ^= Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return `${text.length}:${4294967296 * (2097151 & h2) + (h1 >>> 0)}`;
}

/** Holds `draft` in this tab alone. False, as `writeDraft` says of a draft the browser did not keep. */
function holdInTab(draft: CanvasDraft): false {
  tabOnly.set(draft.artifact_id, draft);
  stopAsking ??= guardUnload();
  return false;
}

function dropFromTab(id: string): void {
  if (!tabOnly.delete(id) || tabOnly.size > 0) return;
  stopAsking?.();
  stopAsking = null;
}

/** Removes what the browser keeps under `key`. When it kept something, room was made, and the
 *  draft it refused is worth another try. */
function unstore(key: string): void {
  if (keys(PREFIX).includes(key)) refused = null;
  writeText(key, null);
}

/** What a tab starts with: no draft held, none refused. Tests share one tab, and call this between them. */
export function forgetTabDrafts(): void {
  for (const id of [...tabOnly.keys()]) dropFromTab(id);
  refused = null;
}

function storedDraft(id: string): CanvasDraft | null {
  const value = readJson(PREFIX + id);
  return isDraft(value) && value.artifact_id === id ? value : null;
}

/** The draft kept for canvas `id`, this tab's own before a stored one, or null when there is none
 *  or it is not one. */
export function readDraft(id: string): CanvasDraft | null {
  return tabOnly.get(id) ?? storedDraft(id);
}

/**
 * Keeps `draft`, or removes it when its text is back to its base and no save it sent may land.
 * False when the browser did not keep it, and this tab holds it instead. The older draft is removed
 * first: a write the quota refuses must not leave a draft older than what the person has since
 * typed, which reopening would merge back in. A refused write makes room by removing other
 * canvases' drafts, the oldest first and one at a time, until it fits: what the person types now
 * outweighs what they left. When no room can be made, the others stay as they were, and the
 * browser is not asked again until this canvas's draft is lighter or a stored draft has gone: a
 * write follows every pause in typing, and each try reads and rewrites every other draft.
 */
export function writeDraft(draft: CanvasDraft): boolean {
  const id = draft.artifact_id;
  const key = PREFIX + id;
  if (draft.text === draft.base && draft.sent.length === 0) {
    dropFromTab(id);
    unstore(key);
    return true;
  }
  // Counted in characters rather than as the JSON to be stored, which is the cost being spared.
  const weight = draft.base.length + draft.text.length;
  if (refused?.id === id && weight >= refused.weight) return holdInTab(draft);
  // A browser that refuses even a removal keeps nothing at all: there is no quota to remember.
  if (!writeText(key, null)) return holdInTab(draft);
  if (!store(key, JSON.stringify(draft))) {
    refused = { id, weight };
    return holdInTab(draft);
  }
  refused = null;
  dropFromTab(id);
  // Values are read only when there are too many: a write follows every pause in typing.
  if (keys(PREFIX).length > KEEP) pruneDrafts(draft.saved_at, id);
  return true;
}

/**
 * Stores `json` under `key`, freeing room as `writeDraft` says when the browser refuses it. When
 * even every other draft gone leaves no room, they are put back as they were: losing what other
 * canvases kept would buy the person nothing.
 */
function store(key: string, json: string): boolean {
  if (writeText(key, json)) return true;
  const freed: Array<[string, string]> = [];
  for (const other of othersOldestFirst()) {
    const text = readText(other);
    writeText(other, null);
    if (text !== null) freed.push([other, text]);
    if (writeText(key, json)) return true;
  }
  for (const [other, text] of freed) {
    if (!writeText(other, text)) console.error(`A canvas draft taken out to make room could not be put back: ${other}`);
  }
  return false;
}

/** The keys of the drafts kept, the longest kept first; an entry that is no draft goes first of all.
 *  `writeDraft` has taken its own key out by now, so these are other canvases'. */
function othersOldestFirst(): string[] {
  const aged = keys(PREFIX).map((other) => {
    const value = readJson(other);
    return { other, savedAt: isDraft(value) ? value.saved_at : Number.NEGATIVE_INFINITY };
  });
  return aged.sort((x, y) => (x.savedAt < y.savedAt ? -1 : x.savedAt > y.savedAt ? 1 : 0)).map(({ other }) => other);
}

/** Removes canvas `id`'s draft, this tab's and the stored one; given `text`, each only while it
 *  still holds that text, so a save that was overtaken by more typing, here or in another tab,
 *  leaves the newer draft in place. */
export function clearDraft(id: string, text?: string): void {
  if (text === undefined || tabOnly.get(id)?.text === text) dropFromTab(id);
  if (text === undefined || storedDraft(id)?.text === text) unstore(PREFIX + id);
}

/**
 * Drops drafts that are broken or older than thirty days, then all but the ten saved last.
 * `spare` names a canvas whose draft stays whatever its age: the one just written.
 */
export function pruneDrafts(now: number, spare: string | null = null): void {
  const kept: { key: string; savedAt: number }[] = [];
  for (const key of keys(PREFIX)) {
    const value = readJson(key);
    const fresh = isDraft(value) && now - value.saved_at <= MAX_AGE_MS;
    if (key === PREFIX + spare) kept.push({ key, savedAt: Number.POSITIVE_INFINITY });
    else if (fresh) kept.push({ key, savedAt: value.saved_at });
    else writeText(key, null);
  }
  kept.sort((x, y) => y.savedAt - x.savedAt);
  for (const { key } of kept.slice(KEEP)) writeText(key, null);
}
