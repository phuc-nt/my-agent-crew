import { type ReactNode, useCallback } from "react";
import { vi } from "../i18n/vi";
import { splitRelated } from "../lib/wiki-links";
import { MarkdownBody } from "./markdown-body";

interface Props {
  body: string;
  /** slug → title of every page in the vault, so a link knows whether it leads anywhere. */
  titles: ReadonlyMap<string, string>;
  onOpen: (slug: string) => void;
}

/**
 * A page as prose: its markdown rendered, each `[[Link]]` a way to the page it names.
 *
 * A link to a page nobody has written yet is not a dead button: it is drawn as missing,
 * and says so to a screen reader, because in a vault that is a gap worth filling rather
 * than a mistake to hide. The machine's "Liên quan" block is lifted out of the prose and
 * drawn as chips, since as markdown it would print its HTML comment markers.
 */
export function WikiReadView({ body, titles, onOpen }: Props) {
  const { authored, related } = splitRelated(body);

  const wikiLink = useCallback(
    (slug: string, label: ReactNode) =>
      titles.has(slug) ? (
        <button type="button" className="link-button wiki-link" onClick={() => onOpen(slug)}>
          {label}
        </button>
      ) : (
        <span className="wiki-link missing" title={vi.wiki.missingLink}>
          {label}
          <span className="sr-only"> ({vi.wiki.missingLink})</span>
        </span>
      ),
    [titles, onOpen],
  );

  return (
    <div className="wiki-read">
      {authored ? (
        <MarkdownBody text={authored} wikiLink={wikiLink} />
      ) : (
        <p className="muted">{vi.wiki.bodyEmpty}</p>
      )}
      {related.length > 0 && (
        <nav aria-label={vi.wiki.related}>
          <h4 className="wiki-page-label">{vi.wiki.related}</h4>
          <ul className="wiki-related">
            {related.map((slug) => (
              <li key={slug}>
                <button type="button" className="chip" onClick={() => onOpen(slug)}>
                  {titles.get(slug) ?? slug}
                </button>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </div>
  );
}
