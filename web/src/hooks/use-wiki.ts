import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { WikiList, WikiPage, WikiPageEdit, WikiReport } from "../api/types";

export interface WikiController {
  list: WikiList | null;
  page: WikiPage | null;
  report: WikiReport | null;
  query: string;
  busy: boolean;
  search: (q: string) => Promise<void>;
  open: (slug: string) => Promise<void>;
  close: () => void;
  save: (slug: string, body: WikiPageEdit) => Promise<void>;
  remove: (slug: string) => Promise<void>;
  compile: () => Promise<void>;
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
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);

  const reload = useCallback(
    async (q: string) => {
      const [pages, problems] = await Promise.all([
        api.listWiki(agentId, q || undefined),
        api.getWikiReport(agentId),
      ]);
      setList(pages);
      setReport(problems);
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
      // the list and the report are both re-read rather than patched in place.
      await reload(query);
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
      await api.compileWiki(agentId);
    } finally {
      setBusy(false);
    }
  }, [agentId]);

  return { list, page, report, query, busy, search, open, close, save, remove, compile };
}
