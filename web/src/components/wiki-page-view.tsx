import type { WikiPage } from "../api/types";
import { vi } from "../i18n/vi";
import { MemoryEditor } from "./memory-editor";

interface Props {
  page: WikiPage;
  onBack: () => void;
  onSaveBody: (body: string) => Promise<void>;
  onRemove: () => Promise<void>;
}

/**
 * One page, open for reading and editing.
 *
 * The sources and the open questions are shown but not editable here: they are the
 * page's evidence, and a text box next to the body invites rewriting them to match what
 * the body now says, which is exactly backwards.
 */
export function WikiPageView({ page, onBack, onSaveBody, onRemove }: Props) {
  const remove = () => {
    if (window.confirm(vi.wiki.confirmRemove(page.title))) void onRemove();
  };

  return (
    <div data-testid="wiki-page">
      <div className="wiki-page-head">
        <button type="button" className="ghost" onClick={onBack}>
          ← {vi.wiki.back}
        </button>
        <button type="button" className="ghost" onClick={remove}>
          {vi.memory.remove}
        </button>
      </div>

      <h3 className="wiki-page-title">{page.title}</h3>
      <p className="muted">
        {vi.wiki.kinds[page.kind] ?? page.kind}
        {" · "}
        {page.updated ? vi.wiki.updated(page.updated) : vi.wiki.neverUpdated}
        {page.status !== "ok" && <span className="badge warn"> {vi.wiki.needsReview}</span>}
      </p>

      <MemoryEditor label={vi.wiki.body} value={page.body} rows={14} onSave={onSaveBody} />

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
            {page.questions.map((question) => (
              <li key={question}>{question}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
