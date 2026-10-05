/**
 * Every canvas there is, newest first, whatever conversation it was written in: what each one is,
 * who made it, where it came from and what all its versions hold, with a search by name and a
 * delete. A canvas's name opens it on a page of its own.
 *
 * A delete takes away the row the keyboard was on. The keyboard then goes to the name of the row
 * that took its place, to the last row when none did, to the search box when no row is left, and a
 * line says which canvas is gone. A person who took the keyboard elsewhere while the server was
 * answering keeps it there, and a delete the server refused moves nothing.
 *
 * A title, a path and an agent's name are words someone else chose: they are drawn as text, with
 * the characters nobody would see in them written out. Where a canvas came from is said, never
 * linked, and a web address is given as the agent's word for it, which nothing here checked.
 */

import { useEffect, useRef, useState } from "react";
import type { ArtifactSummary } from "../../api/artifact-types";
import { useCanvasLibrary } from "../../hooks/use-canvas-library";
import { useNow } from "../../hooks/use-now";
import { vi } from "../../i18n/vi";
import { authorLabel } from "../../lib/canvas-author";
import { parseSource } from "../../lib/canvas-source";
import { TITLE_MAX } from "../../lib/canvas-title";
import { formatBytes } from "../../lib/format-bytes";
import { showHiddenChars, showPathChars } from "../../lib/hidden-chars";
import { timeAgo } from "../../lib/relative-time";
import { Icon } from "../ui/icon";

const { canvas } = vi;

type AgentName = (id: string) => string;
type Props = { connected: boolean; agentName: AgentName; onOpen(id: string): void };
/** The canvas last deleted: the name its row showed, and where in the list that row stood. */
type Gone = { title: string; at: number };

export function CanvasLibrary({ connected, agentName, onOpen }: Props) {
  const library = useCanvasLibrary(connected);
  const now = useNow(60_000);
  const { items, usage, searched, failed } = library;
  const root = useRef<HTMLElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const [gone, setGone] = useState<Gone | null>(null);

  // Runs once the row is out of the page, which leaves a keyboard that was on it nowhere.
  useEffect(() => {
    if (gone === null || document.activeElement !== document.body) return;
    const names = root.current?.querySelectorAll<HTMLElement>(".canvas-library-title");
    (names?.[Math.min(gone.at, names.length - 1)] ?? search.current)?.focus();
  }, [gone]);

  const remove = async (id: string, title: string, at: number) => {
    setGone(null);
    if (await library.remove(id)) setGone({ title, at });
  };

  return (
    <section className="canvas-library" data-testid="canvas-library" ref={root}>
      <div className="canvas-library-head">
        <input
          ref={search}
          type="search"
          aria-label={canvas.librarySearch}
          placeholder={canvas.librarySearch}
          value={library.query}
          // No title is longer, so no longer name can be found.
          maxLength={TITLE_MAX}
          onChange={(event) => library.setQuery(event.currentTarget.value)}
        />
        {usage && (
          <p className="muted canvas-library-total">
            {canvas.libraryTotal(usage.count, formatBytes(usage.bytes), formatBytes(usage.cap))}
          </p>
        )}
      </div>
      {failed && (
        <div className="notice error canvas-notice" role="alert">
          <Icon name="alert" />
          <span>{canvas.libraryFailed}</span>
          <button type="button" className="link-button" onClick={library.retry}>
            {canvas.retry}
          </button>
        </div>
      )}
      {/* There from the start: a screen reader hears a line it knows fill, and may miss a new one. */}
      <p className="muted canvas-library-said" role="status">
        {gone ? canvas.libraryDeleted(gone.title) : ""}
      </p>
      {items === null && !failed && <p className="muted">{canvas.libraryLoading}</p>}
      {items?.length === 0 && <p className="muted">{searched ? canvas.libraryNoMatch : canvas.libraryEmpty}</p>}
      {items !== null && items.length > 0 && (
        <>
          <ul className="canvas-library-list">
            {items.map((item, at) => (
              <Row
                key={item.id}
                item={item}
                size={usage?.by_artifact[item.id]}
                when={timeAgo(item.updated_at, now)}
                agentName={agentName}
                refused={library.refused.has(item.id)}
                onOpen={() => onOpen(item.id)}
                onDelete={(title) => void remove(item.id, title, at)}
              />
            ))}
          </ul>
          {/* The server lists so many at once: the count says whether there are more. */}
          {!searched && usage !== null && usage.count > items.length && (
            <p className="muted canvas-library-capped">{canvas.libraryCapped(items.length)}</p>
          )}
        </>
      )}
    </section>
  );
}

/** Where a canvas says it came from, in words: a file by its agent and path, a page by its host. */
function sourceText(source: string, agentName: AgentName): string | null {
  const parsed = parseSource(source);
  if (parsed === null) return null;
  if (parsed.kind === "url") return canvas.librarySourceDeclared(parsed.host);
  return `${showHiddenChars(agentName(parsed.agentId))}/${showPathChars(parsed.path)}`;
}

type RowProps = {
  item: ArtifactSummary;
  /** What every version of the canvas holds, in bytes, when the count names it. */
  size: number | undefined;
  when: string;
  agentName: AgentName;
  refused: boolean;
  onOpen(): void;
  /** Asked for and agreed to, with the name the row shows. */
  onDelete(title: string): void;
};

function Row({ item, size, when, agentName, refused, onOpen, onDelete }: RowProps) {
  const title = showHiddenChars(item.title || canvas.untitled);
  const kind = canvas.kinds[item.kind] ?? item.kind;
  // The server writes "" for a canvas a person made, so an agent whose id is "user" stays an agent.
  const maker = showHiddenChars(authorLabel(item.agent_id ? `agent:${item.agent_id}` : "user", agentName));
  const source = sourceText(item.source, agentName);
  return (
    <li className="canvas-library-row" data-testid="canvas-library-row">
      <div className="canvas-library-row-head">
        <button type="button" className="canvas-library-title" onClick={onOpen}>
          {title}
        </button>
        <span className="badge">{item.kind === "code" && item.language ? `${kind} · ${item.language}` : kind}</span>
        <button
          type="button"
          className="icon-button"
          aria-label={canvas.deleteLabel(title)}
          title={canvas.deleteLabel(title)}
          onClick={() => {
            if (window.confirm(canvas.deleteConfirm(title))) onDelete(title);
          }}
        >
          <Icon name="trash" />
        </button>
      </div>
      <p className="muted canvas-library-meta">{`v${item.head_version} · ${canvas.libraryCreatedBy} ${maker} · ${when}`}</p>
      {source !== null && <p className="muted canvas-library-source">{source}</p>}
      {typeof size === "number" && <p className="muted">{`${formatBytes(size)} ${canvas.libraryAllVersions}`}</p>}
      {refused && (
        <p className="canvas-library-refused" role="alert">
          {canvas.deleteFailed}
        </p>
      )}
    </li>
  );
}
