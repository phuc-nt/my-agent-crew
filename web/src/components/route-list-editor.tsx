import type { RouteInfo } from "../api/types";
import { vi } from "../i18n/vi";

interface Props {
  routes: RouteInfo[];
  /** Provider names the crew actually built, so the list offers only what can answer. */
  providers: string[];
  readOnly: boolean;
  onChange: (next: RouteInfo[]) => void;
  testId?: string;
}

/** A new row starts on a real provider: `fake` only echoes the prompt back, and sorts first. */
const firstReal = (providers: string[]) => providers.find((name) => name !== "fake") ?? providers[0] ?? "";

/**
 * An ordered list of provider + model pairs, tried top to bottom: an agent's own routes,
 * or the ones every agent falls back on. The last row cannot be removed — a list with no
 * route leaves nothing to answer with.
 */
export function RouteListEditor({ routes, providers, readOnly, onChange, testId }: Props) {
  const edit = (i: number, patch: Partial<RouteInfo>) =>
    onChange(routes.map((route, at) => (at === i ? { ...route, ...patch } : route)));

  return (
    <>
      <ol className="route-editor" data-testid={testId ?? "route-editor"}>
        {routes.map((route, i) => (
          <li key={i} className="row">
            <select
              aria-label={vi.editor.provider}
              value={route.provider}
              disabled={readOnly}
              onChange={(e) => edit(i, { provider: e.target.value })}
            >
              {/* The current provider stays selectable even when the crew did not build
                  it: dropping it silently would rewrite a route the person never touched
                  the moment they changed something else on the form. */}
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
              onClick={() => onChange(routes.filter((_, at) => at !== i))}
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
        onClick={() => onChange([...routes, { provider: firstReal(providers), model: "" }])}
      >
        {vi.editor.addRoute}
      </button>
    </>
  );
}
