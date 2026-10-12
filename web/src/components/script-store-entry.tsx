import { useId, useState } from "react";
import { ApiError } from "../api/client";
import type { ScriptStoreEntry } from "../api/script-store";
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
  /** Reads the whole value. */
  onRead(): Promise<string>;
  /** The server answered that the key is no longer there. */
  onGone(): void;
  /** Asked for; the list asks the person before anything goes. */
  onDelete(): void;
}

/** What the box under the key holds, and which writing of the key it was asked for. */
type Shown = { stamp: string } & ({ state: "reading" } | { state: "read"; text: string } | { state: "failed"; why: string });

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
  // A value read before the key was written again is no longer the key's value.
  const box = shown?.stamp === entry.updated_at ? shown : null;

  const read = async () => {
    const stamp = entry.updated_at;
    /** Only the read still waited for fills the box: a person may have closed it since. */
    const settle = (next: Shown) => setShown((was) => (was?.stamp === stamp && was.state === "reading" ? next : was));
    setShown({ stamp, state: "reading" });
    try {
      const text = await onRead();
      settle({ stamp, state: "read", text });
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setShown(null);
        onGone();
      } else {
        settle({ stamp, state: "failed", why: errorText(error) });
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
