import type { MemoryProposal } from "../api/types";
import { vi } from "../i18n/vi";
import { DiffView } from "./diff-view";

/** One page as a compile writes it; `previous_body` holds the same shape for pages it overwrites. */
interface PlannedPage {
  slug: string;
  kind: string;
  title: string;
  body: string;
  sources: string[];
  questions: string[];
  status: string;
}

/**
 * The JSON a compile stored, read defensively: the column is text, and a proposal from an
 * older build or a hand-edited row should still be reviewable as text rather than break
 * the whole proposals tab.
 */
function parsePages(text: string): PlannedPage[] | null {
  try {
    const value: unknown = JSON.parse(text || "[]");
    if (!Array.isArray(value)) return null;
    return value
      .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
      .map((item) => ({
        slug: String(item.slug ?? ""),
        kind: String(item.kind ?? ""),
        title: String(item.title ?? item.slug ?? ""),
        body: String(item.body ?? ""),
        sources: Array.isArray(item.sources) ? item.sources.map(String) : [],
        questions: Array.isArray(item.questions) ? item.questions.map(String) : [],
        status: String(item.status ?? "ok"),
      }));
  } catch {
    return null;
  }
}

/**
 * A compile proposes a whole batch in one approval, so it is shown as one card per page:
 * which are new and which overwrite a page that exists, and for an overwrite, exactly
 * which lines change. The server only records a "previous" for pages that existed, which
 * is what tells the two apart.
 */
export function CompileProposalView({ proposal }: { proposal: MemoryProposal }) {
  const pages = parsePages(proposal.body);
  if (pages === null) return <pre className="diff">{proposal.body}</pre>;
  const previous = new Map((parsePages(proposal.previous_body) ?? []).map((p) => [p.slug, p]));

  return (
    <ul className="compile-pages" aria-label={vi.memory.compilePages(pages.length)}>
      {pages.map((page) => {
        const before = previous.get(page.slug);
        return (
          <li key={page.slug} className="compile-page">
            <div className="fact-head">
              <span className={before ? "badge warn" : "badge ok"}>
                {before ? vi.memory.compileUpdated : vi.memory.compileNew}
              </span>
              <strong>{page.title}</strong>
              {page.status !== "ok" && <span className="badge warn">{vi.wiki.needsReview}</span>}
            </div>
            <div className="muted">
              {vi.wiki.kinds[page.kind] ?? page.kind} · {vi.memory.compileSources(page.sources.length)}
              {page.questions.length > 0 && ` · ${vi.memory.compileQuestions(page.questions.length)}`}
            </div>
            <details>
              <summary>{before ? vi.memory.compileShowChanges : vi.memory.compileShowBody}</summary>
              {before ? (
                <DiffView before={before.body} after={page.body} />
              ) : (
                <pre className="diff">{page.body}</pre>
              )}
            </details>
          </li>
        );
      })}
    </ul>
  );
}
