import { useId, useState } from "react";
import { ApiError } from "../api/client";
import type { ScriptStoreEntry, ScriptStoreValue } from "../api/script-store";
import { vi } from "../i18n/vi";
import { errorText } from "../lib/error-text";
import { showHiddenChars } from "../lib/hidden-chars";
import { prettyJson } from "../lib/pretty-json";
import { formatDateTime } from "./run-timeline";

const { scriptStore: words } = vi;

interface Props {
  entry: ScriptStoreEntry;
  /** Why the server refused to delete this key, when it just did. */
  refused: string | null;
  /** Reads the whole value, with when it was written. */
  onRead(): Promise<ScriptStoreValue>;
  /** The server answered that the key is no longer there. */
  onGone(): void;
  /** Asked for; the list asks the person before anything goes. */
  onDelete(): void;
}

/** What the box under the key holds. `row` is the writing of the key the list showed when
 *  the value was asked for; a value that was read says which writing it is itself (`stamp`),
 *  a later one than the row's when the key was written in between. */
type Shown = { row: string } & (
  | { state: "reading" }
  | { state: "read"; text: string; stamp: string }
  | { state: "failed"; why: string }
);

/**
 * One key a script kept: its name, how its value opens, how long the value is and when it
 * was last written, with the whole value a press away and a delete.
 *
 * The whole value is read when asked for, never with the list: one may run to tens of
 * thousands of characters. It is set out as JSON when it is JSON and shown as it is kept
 * otherwise, in a box that scrolls on its own. A key and a value are text a script took
 * from wherever its tools read, so the characters nobody would see in them are written out.
 */
export function ScriptStoreEntryRow({ entry, refused, onRead, onGone, onDelete }: Props) {
  const [shown, setShown] = useState<Shown | null>(null);
  const boxId = useId();
  const key = showHiddenChars(entry.key);
  // The box is the key's while the row is the writing it was asked under, or the writing
  // the value says it is once the list has caught up with it. A row that moved on to any
  // other writing has a value nobody read: one read before it is no longer the key's.
  const written = shown === null ? [] : shown.state === "read" ? [shown.row, shown.stamp] : [shown.row];
  const box = written.includes(entry.updated_at) ? shown : null;

  const read = async () => {
    const row = entry.updated_at;
    /** Only the read still waited for fills the box: a person may have closed it since. */
    const settle = (next: Shown) => setShown((was) => (was?.row === row && was.state === "reading" ? next : was));
    setShown({ row, state: "reading" });
    try {
      const value = await onRead();
      settle({ row, state: "read", text: value.text, stamp: value.updated_at });
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setShown(null);
        onGone();
      } else {
        settle({ row, state: "failed", why: errorText(error) });
      }
    }
  };

  const pretty = box?.state === "read" ? prettyJson(box.text) : null;
  return (
    <li className="script-store-entry" data-testid="script-store-entry">
      <div className="script-store-entry-head">
        <code className="script-store-key">{key}</code>
        <span className="muted tabular script-store-entry-meta">
          {words.entryChars(entry.chars)}
          {" · "}
          <time dateTime={entry.updated_at}>{formatDateTime(entry.updated_at)}</time>
        </span>
        <span className="script-store-entry-actions">
          <button
            type="button"
            className="ghost script-store-view"
            aria-expanded={box !== null}
            aria-controls={box?.state === "read" ? boxId : undefined}
            aria-label={box === null ? words.viewLabel(key) : words.hideLabel(key)}
            onClick={() => (box === null ? void read() : setShown(null))}
          >
            {box === null ? words.view : words.hide}
          </button>
          <button type="button" className="ghost script-store-delete" aria-label={words.deleteKeyLabel(key)} onClick={onDelete}>
            {words.deleteKey}
          </button>
        </span>
      </div>
      {box?.state === "read" ? (
        <>
          {/* In the tab order, so a value taller than its box can be scrolled without a mouse. */}
          <pre
            className="script-store-value"
            id={boxId}
            data-testid="script-store-value"
            role="group"
            aria-label={words.valueLabel(key)}
            tabIndex={0}
          >
            {showHiddenChars(pretty ?? box.text)}
          </pre>
          {pretty === null && <p className="muted script-store-note">{words.valueRaw}</p>}
        </>
      ) : (
        <p className="script-store-preview" data-testid="script-store-preview">
          {showHiddenChars(entry.preview)}
        </p>
      )}
      {box?.state === "reading" && <p className="muted script-store-note">{words.valueLoading}</p>}
      {box?.state === "failed" && (
        <p className="script-store-refused" role="alert">
          {box.why}{" "}
          <button type="button" className="link-button" onClick={() => void read()}>
            {vi.retry}
          </button>
        </p>
      )}
      {refused !== null && (
        <p className="script-store-refused" role="alert">
          {refused}
        </p>
      )}
    </li>
  );
}
