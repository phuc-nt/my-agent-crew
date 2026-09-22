import type { WikiPage, WikiPageSummary, WikiProblem } from "../api/types";

const KINDS = ["entities", "concepts", "syntheses"];

function json(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

export function wikiPage(overrides: Partial<WikiPage> = {}): WikiPage {
  return {
    slug: "han-eco",
    kind: "entities",
    title: "Hạn Eco",
    body: "Hạn nộp hồ sơ là thứ tư.",
    sources: ["note:2026-09-19"],
    questions: [],
    status: "ok",
    updated: "2026-09-20",
    ...overrides,
  };
}

/**
 * The wiki half of the fake server, kept apart so the vault can be set up per test
 * without every memory test carrying a vault it never looks at.
 */
export class FakeWiki {
  pages = new Map<string, WikiPage>();
  problems: WikiProblem[] = [];
  /** When true the next compile answers 409, as the nightly rewrite holding the folder would. */
  busy = false;
  /** Agents a compile was asked for, newest last. */
  compiled: string[] = [];

  add(page: Partial<WikiPage> = {}): WikiPage {
    const full = wikiPage(page);
    this.pages.set(full.slug, full);
    return full;
  }

  private summary(page: WikiPage): WikiPageSummary {
    const { body: _body, questions, ...rest } = page;
    return { ...rest, question_count: questions.length };
  }

  /** Handles every `/agents/{id}/memory/wiki…` path; null when the path is not one. */
  route(
    path: string,
    method: string,
    body: Partial<WikiPage>,
    params: URLSearchParams,
    knownAgent: (id: string) => boolean,
  ): Response | null {
    const match = path.match(/^\/agents\/([^/]+)\/memory\/wiki(\/.*)?$/);
    if (!match) return null;
    const [, agentId, rest = ""] = match;
    if (!knownAgent(agentId)) return json({ detail: "agent not found" }, 404);

    if (rest === "/compile" && method === "POST") {
      if (this.busy) return json({ detail: "đang xử lý" }, 409);
      this.compiled.push(agentId);
      return json({ agent_id: agentId, run_source: "memory:wiki" }, 202);
    }
    if (rest === "/report") {
      return json({
        problems: this.problems,
        questions: [...this.pages.values()].flatMap((p) =>
          p.questions.map((question) => ({ slug: p.slug, question })),
        ),
      });
    }

    const slug = rest.match(/^\/pages\/(.+)$/)?.[1];
    if (slug) return this.pageRoute(decodeURIComponent(slug), method, body);
    if (rest === "") {
      const q = (params.get("q") ?? "").toLowerCase();
      const pages = [...this.pages.values()].filter(
        (p) => !q || p.title.toLowerCase().includes(q) || p.body.toLowerCase().includes(q),
      );
      return json({ pages: pages.map((p) => this.summary(p)), kinds: KINDS, count: pages.length });
    }
    return null;
  }

  private pageRoute(slug: string, method: string, body: Partial<WikiPage>): Response {
    const page = this.pages.get(slug);
    if (!page) return json({ detail: "page not found" }, 404);
    if (method === "DELETE") {
      this.pages.delete(slug);
      return json({ slug, deleted: true });
    }
    if (method === "PUT") {
      // Only the fields actually sent, so the fake makes the same promise the server does.
      const sent = Object.fromEntries(Object.entries(body).filter(([, v]) => v !== undefined));
      const next = { ...page, ...sent };
      this.pages.set(slug, next);
      return json(next);
    }
    return json(page);
  }
}
