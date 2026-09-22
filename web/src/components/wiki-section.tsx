import { useState } from "react";
import { ApiError } from "../api/client";
import type { AgentInfo, WikiPageSummary } from "../api/types";
import { useWiki } from "../hooks/use-wiki";
import { vi } from "../i18n/vi";
import { WikiPageView } from "./wiki-page-view";

interface Props {
  agents: AgentInfo[];
  agentId: string;
  onSelectAgent: (id: string) => void;
}

function byKind(pages: WikiPageSummary[]): [string, WikiPageSummary[]][] {
  const groups = new Map<string, WikiPageSummary[]>();
  for (const page of pages) groups.set(page.kind, [...(groups.get(page.kind) ?? []), page]);
  return [...groups];
}

/** One agent's vault: the pages it has settled on, grouped the way they are filed. */
export function WikiSection(props: Props) {
  const wiki = useWiki(props.agentId);
  const [message, setMessage] = useState("");

  const compile = async () => {
    try {
      await wiki.compile();
      setMessage(vi.wiki.compileStarted);
    } catch (error) {
      // 409 means the nightly rewrite holds the memory folder; anything else just failed.
      const busy = error instanceof ApiError && error.status === 409;
      setMessage(busy ? vi.wiki.compileBusy : vi.wiki.compileFailed);
    }
  };

  const problems = wiki.report?.problems ?? [];

  return (
    <div data-testid="wiki-section">
      <label>
        {vi.agents}
        <select
          value={props.agentId}
          onChange={(event) => props.onSelectAgent(event.currentTarget.value)}
        >
          {props.agents.map((agent) => (
            <option key={agent.id} value={agent.id}>
              {agent.name}
            </option>
          ))}
        </select>
      </label>

      {wiki.page ? (
        <WikiPageView
          page={wiki.page}
          onBack={wiki.close}
          onSaveBody={(body) => wiki.save(wiki.page?.slug ?? "", { body })}
          onRemove={() => wiki.remove(wiki.page?.slug ?? "")}
        />
      ) : (
        <>
          <div className="wiki-toolbar">
            <input
              type="search"
              aria-label={vi.wiki.searchPlaceholder}
              placeholder={vi.wiki.searchPlaceholder}
              value={wiki.query}
              onChange={(event) => void wiki.search(event.currentTarget.value)}
            />
            <button
              type="button"
              disabled={wiki.busy}
              title={vi.wiki.compileHint}
              onClick={() => void compile()}
            >
              {vi.wiki.compile}
            </button>
          </div>
          {message && <p className="muted">{message}</p>}

          {!wiki.list || wiki.list.count === 0 ? (
            <p className="muted">{wiki.query ? vi.wiki.searchEmpty : vi.wiki.empty}</p>
          ) : (
            <>
              <p className="muted">{vi.wiki.count(wiki.list.count)}</p>
              {byKind(wiki.list.pages).map(([kind, pages]) => (
                <section key={kind}>
                  <h4 className="wiki-section-kind">{vi.wiki.kinds[kind] ?? kind}</h4>
                  <ul className="wiki-list">
                    {pages.map((page) => (
                      <li key={page.slug}>
                        <button type="button" className="ghost" onClick={() => void wiki.open(page.slug)}>
                          {page.title}
                        </button>
                        {page.sources.length === 0 && (
                          <span className="badge warn"> {vi.wiki.noSources}</span>
                        )}
                        {page.question_count > 0 && (
                          <span className="muted"> · {page.question_count} ?</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </>
          )}

          <h4 className="wiki-section-kind">{vi.wiki.problems}</h4>
          {problems.length === 0 ? (
            <p className="muted">{vi.wiki.problemsEmpty}</p>
          ) : (
            <ul className="wiki-problems">
              {problems.map((problem) => (
                <li key={`${problem.kind}:${problem.slug}:${problem.detail}`}>
                  <button type="button" className="ghost" onClick={() => void wiki.open(problem.slug)}>
                    {problem.slug}
                  </button>
                  <span className="muted">
                    {" "}
                    — {vi.wiki.problemKinds[problem.kind] ?? problem.kind}: {problem.detail}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
