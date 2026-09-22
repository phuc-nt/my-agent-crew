import type { RouteInfo } from "../../api/types";
import type { AgentDraft } from "../../hooks/use-agent-draft";
import { vi } from "../../i18n/vi";

interface Props {
  form: AgentDraft;
  readOnly: boolean;
  /** Provider names the crew actually built, so the list offers only what can answer. */
  providers: string[];
}

/**
 * The models the agent tries, in order.
 *
 * Order is the whole point of the list — the second route only runs when the first one
 * fails — so the rows are moved with explicit up/down rather than left to whatever order
 * a text field happens to hold.
 */
export function ModelSection({ form, readOnly, providers }: Props) {
  const routes = form.draft.routes ?? [];

  const put = (next: RouteInfo[]) => form.set("routes", next);
  const edit = (i: number, patch: Partial<RouteInfo>) =>
    put(routes.map((route, at) => (at === i ? { ...route, ...patch } : route)));

  return (
    <section className="editor-section" data-testid="section-model">
      <h3>{vi.editor.sectionModel}</h3>
      <p className="muted">{vi.editor.routesHint}</p>
      <ol className="route-editor" data-testid="route-editor">
        {routes.map((route, i) => (
          <li key={i} className="row">
            <select
              aria-label={vi.editor.provider}
              value={route.provider}
              disabled={readOnly}
              onChange={(e) => edit(i, { provider: e.target.value })}
            >
              {/* The agent's current provider stays selectable even when the crew did not
                  build it: dropping it silently would rewrite a route the person never
                  touched the moment they changed something else on the form. */}
              {[...new Set([...providers, route.provider])].map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
            <input
              type="text"
              aria-label={vi.editor.model}
              value={route.model}
              disabled={readOnly}
              onChange={(e) => edit(i, { model: e.target.value })}
            />
            <button
              type="button"
              className="ghost"
              disabled={readOnly || routes.length === 1}
              onClick={() => put(routes.filter((_, at) => at !== i))}
            >
              {vi.editor.remove}
            </button>
          </li>
        ))}
      </ol>
      <button
        type="button"
        className="ghost"
        disabled={readOnly}
        onClick={() => put([...routes, { provider: providers[0] ?? "", model: "" }])}
      >
        {vi.editor.addRoute}
      </button>
    </section>
  );
}
