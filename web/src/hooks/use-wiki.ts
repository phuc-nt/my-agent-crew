import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { WikiList, WikiPage, WikiPageEdit, WikiReport } from "../api/types";
import type { RunStart } from "./use-started-run";

export interface WikiController {
  list: WikiList | null;
  page: WikiPage | null;
  report: WikiReport | null;
  /** slug → title of every page, searched for or not, so a link knows where it leads. */
  titles: ReadonlyMap<string, string>;
  query: string;
  busy: boolean;
  search: (q: string) => Promise<void>;
  open: (slug: string) => Promise<void>;
  close: () => void;
  save: (slug: string, body: WikiPageEdit) => Promise<void>;
  remove: (slug: string) => Promise<void>;
  compile: () => Promise<RunStart>;
  /** Re-reads the list and the report as they stand, e.g. after a compile run ended. */
  refresh: () => Promise<void>;
}

/**
 * The vault of one agent, for the Wiki tab.
 *
 * The list and the open page are fetched separately on purpose: the list carries no
 * bodies, so browsing a large vault costs one small response rather than all of it.
 */
export function useWiki(agentId: string): WikiController {
  const [list, setList] = useState<WikiList | null>(null);
  const [page, setPage] = useState<WikiPage | null>(null);
  const [report, setReport] = useState<WikiReport | null>(null);
  const [titles, setTitles] = useState<ReadonlyMap<string, string>>(new Map());
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);

  const reload = useCallback(
    async (q: string) => {
      // While a search narrows the list, links in an open page still point anywhere in
      // the vault; resolving them against the narrowed list would call real pages missing.
      const [pages, problems, all] = await Promise.all([
        api.listWiki(agentId, q || undefined),
        api.getWikiReport(agentId),
        q ? api.listWiki(agentId) : null,
      ]);
      setList(pages);
      setReport(problems);
      setTitles(new Map((all ?? pages).pages.map((p) => [p.slug, p.title])));
    },
    [agentId],
  );

  useEffect(() => {
    if (!agentId) return;
    // Switching agent must not leave the previous agent's page on screen: it would read
    // as this agent knowing something it does not.
    setPage(null);
    setQuery("");
    reload("").catch(() => {
      setList(null);
      setReport(null);
      setTitles(new Map());
    });
  }, [agentId, reload]);

  const search = useCallback(
    async (q: string) => {
      setQuery(q);
      await reload(q);
    },
    [reload],
  );

  const open = useCallback(
    async (slug: string) => setPage(await api.getWikiPage(agentId, slug)),
    [agentId],
  );

  const close = useCallback(() => setPage(null), []);

  const save = useCallback(
    async (slug: string, body: WikiPageEdit) => {
      setPage(await api.putWikiPage(agentId, slug, body));
      // An edited link changes other pages' backlinks and can clear a lint problem, so
      // the list and the report are both re-read rather than patched in place. The edit
      // has landed by now: a re-read that fails must not make it look as if it had not.
      void reload(query).catch(() => undefined);
    },
    [agentId, query, reload],
  );

  const remove = useCallback(
    async (slug: string) => {
      await api.deleteWikiPage(agentId, slug);
      setPage(null);
      await reload(query);
    },
    [agentId, query, reload],
  );

  const compile = useCallback(async () => {
    setBusy(true);
    try {
      return await api.compileWiki(agentId);
    } finally {
      setBusy(false);
    }
  }, [agentId]);

  const refresh = useCallback(() => reload(query), [query, reload]);

  return { list, page, report, titles, query, busy, search, open, close, save, remove, compile, refresh };
}
