import { useCallback, useState } from "react";
import { ApiError } from "../api/client";
import type { AgentInfo, RunInfo, WikiPageSummary } from "../api/types";
import { useStartedRun } from "../hooks/use-started-run";
import { useWiki } from "../hooks/use-wiki";
import { vi } from "../i18n/vi";
import { RunStatus, runOutcome } from "./run-chip";
import { WikiHeaderPanels } from "./wiki-header-panels";
import { WikiPageView } from "./wiki-page-view";

interface Props {
  agents: AgentInfo[];
  agentId: string;
  /** Every run the activity stream knows, to follow the compile started from here. */
  runs: RunInfo[];
  onSelectAgent: (id: string) => void;
  onReadNote: (day: string) => Promise<string>;
  onSaveNote: (day: string, body: string) => Promise<void>;
}

function byKind(pages: WikiPageSummary[]): [string, WikiPageSummary[]][] {
  const groups = new Map<string, WikiPageSummary[]>();
  for (const page of pages) groups.set(page.kind, [...(groups.get(page.kind) ?? []), page]);
  return [...groups];
}

/** A line about a compile, tied to the agent whose vault it was about. */
type Message = { agentId: string; text: string };

/** One agent's vault: the pages it has settled on, grouped the way they are filed. */
export function WikiSection(props: Props) {
  const wiki = useWiki(props.agentId);
  const [message, setMessage] = useState<Message | null>(null);

  const { refresh } = wiki;
  const { agentId } = props;
  const onSettled = useCallback(
    (run: RunInfo) => {
      setMessage({ agentId: run.agent_id, text: runOutcome(run) });
      // Another agent's vault is on screen now; the one that compiled is re-read on return.
      if (run.agent_id === agentId) void refresh().catch(() => undefined);
    },
    [agentId, refresh],
  );
  const started = useStartedRun(props.runs, onSettled);
  const compiling = started.tracking && started.agentId === props.agentId;

  const compile = async () => {
    setMessage(null);
    try {
      await started.start(wiki.compile);
    } catch (error) {
      // 409 means the nightly rewrite holds the memory folder; anything else just failed.
      const busy = error instanceof ApiError && error.status === 409;
      setMessage({ agentId, text: busy ? vi.wiki.compileBusy : vi.wiki.compileFailed });
    }
  };

  const { open: openPage } = wiki;
  // Stable, so a rendered page does not rebuild its markdown on every parent render.
  const open = useCallback((slug: string) => void openPage(slug).catch(() => undefined), [openPage]);
  const problems = wiki.report?.problems ?? [];
  const questions = wiki.report?.questions ?? [];

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
          key={wiki.page.slug}
          page={wiki.page}
          titles={wiki.titles}
          onBack={wiki.close}
          onOpen={open}
          onSaveBody={(body) => wiki.save(wiki.page?.slug ?? "", { body })}
          onMarkOk={() => wiki.save(wiki.page?.slug ?? "", { status: "ok" })}
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
              disabled={wiki.busy || compiling}
              title={vi.wiki.compileHint}
              onClick={() => void compile()}
            >
              {vi.wiki.compile}
            </button>
          </div>
          <RunStatus
            label={vi.wiki.compileStarted}
            run={started.run}
            tracking={compiling}
            message={message?.agentId === props.agentId ? message.text : ""}
          />
          <WikiHeaderPanels
            agentId={props.agentId}
            questions={questions}
            titles={wiki.titles}
            onOpen={open}
            onReadNote={props.onReadNote}
            onSaveNote={props.onSaveNote}
          />
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
                        <button type="button" className="ghost" onClick={() => open(page.slug)}>
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
                  <button type="button" className="ghost" onClick={() => open(problem.slug)}>
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
