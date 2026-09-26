import { useState } from "react";
import type { WikiPage } from "../api/types";
import { vi } from "../i18n/vi";
import { MemoryEditor } from "./memory-editor";
import { WikiReadView } from "./wiki-read-view";

interface Props {
  page: WikiPage;
  /** slug → title of every page in the vault, for the links in this one. */
  titles: ReadonlyMap<string, string>;
  onBack: () => void;
  onOpen: (slug: string) => void;
  onSaveBody: (body: string) => Promise<void>;
  onMarkOk: () => Promise<void>;
  onRemove: () => Promise<void>;
}

/**
 * One page, open for reading, with editing one button away.
 *
 * It opens rendered because a vault is read far more often than it is written, and the
 * raw text shows `[[links]]` that go nowhere and a machine block of HTML comments.
 * The sources and the open questions are shown but not editable here: they are the
 * page's evidence, and a text box next to the body invites rewriting them to match what
 * the body now says, which is exactly backwards.
 *
 * The parent mounts one per page, so a page reached by a link opens for reading too,
 * without the last page's editor or error carried over.
 */
export function WikiPageView({ page, titles, onBack, onOpen, onSaveBody, onMarkOk, onRemove }: Props) {
  const [editing, setEditing] = useState(false);
  const [marking, setMarking] = useState(false);
  const [markFailed, setMarkFailed] = useState(false);

  const remove = () => {
    if (window.confirm(vi.wiki.confirmRemove(page.title))) void onRemove();
  };

  const markOk = async () => {
    setMarking(true);
    setMarkFailed(false);
    try {
      await onMarkOk();
    } catch {
      setMarkFailed(true);
    } finally {
      setMarking(false);
    }
  };

  const ok = page.status === "ok";
  return (
    <div data-testid="wiki-page">
      <div className="wiki-page-head">
        <button type="button" className="ghost" onClick={onBack}>
          ← {vi.wiki.back}
        </button>
        <span className="wiki-page-actions">
          <button type="button" className="ghost" onClick={() => setEditing((on) => !on)}>
            {editing ? vi.wiki.read : vi.memory.edit}
          </button>
          <button type="button" className="ghost" onClick={remove}>
            {vi.memory.remove}
          </button>
        </span>
      </div>

      <h3 className="wiki-page-title">{page.title}</h3>
      <p className="muted wiki-page-meta">
        {vi.wiki.kinds[page.kind] ?? page.kind}
        {" · "}
        {page.updated ? vi.wiki.updated(page.updated) : vi.wiki.neverUpdated}{" "}
        <span className={ok ? "badge ok" : "badge warn"} data-testid="wiki-status">
          {ok ? vi.wiki.statusOk : vi.wiki.needsReview}
        </span>
        {!ok && (
          <button type="button" className="ghost" disabled={marking} onClick={() => void markOk()}>
            {vi.wiki.markOk}
          </button>
        )}
      </p>
      {markFailed && (
        <p className="notice error" role="alert">
          {vi.wiki.markOkFailed}
        </p>
      )}

      {editing ? (
        <MemoryEditor label={vi.wiki.body} value={page.body} rows={14} onSave={onSaveBody} />
      ) : (
        <WikiReadView body={page.body} titles={titles} onOpen={onOpen} />
      )}

      <h4 className="wiki-page-label">{vi.wiki.sources}</h4>
      {page.sources.length === 0 ? (
        <p className="muted">{vi.wiki.noSources}</p>
      ) : (
        <ul className="wiki-sources">
          {page.sources.map((source) => (
            <li key={source}>{source}</li>
          ))}
        </ul>
      )}

      {page.questions.length > 0 && (
        <>
          <h4 className="wiki-page-label">{vi.wiki.questions}</h4>
          <ul className="wiki-questions">
            {/* Repeats are possible, and the list is never reordered, so position is the key. */}
            {page.questions.map((question, index) => (
              <li key={index}>{question}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
