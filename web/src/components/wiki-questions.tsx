import type { WikiReport } from "../api/types";
import { vi } from "../i18n/vi";

interface Props {
  /** So the header toggle that shows this list can point at it. */
  id: string;
  questions: WikiReport["questions"];
  titles: ReadonlyMap<string, string>;
  onOpen: (slug: string) => void;
}

/**
 * What the vault does not know yet, gathered from every page into one list.
 *
 * Each page keeps its own open questions, so without this the only way to find them is
 * to open every page in turn. Each one leads to the page that asked it, where the answer
 * would go. The header toggle carries the count, so the list itself needs no heading.
 */
export function WikiQuestions({ id, questions, titles, onOpen }: Props) {
  if (questions.length === 0) return null;
  return (
    <section id={id} aria-label={vi.wiki.openQuestions(questions.length)}>
      <ul className="wiki-open-questions">
        {questions.map(({ slug, question }) => (
          <li key={`${slug}:${question}`}>
            <button type="button" className="link-button" onClick={() => onOpen(slug)}>
              {titles.get(slug) ?? slug}
            </button>
            <span>{question}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
