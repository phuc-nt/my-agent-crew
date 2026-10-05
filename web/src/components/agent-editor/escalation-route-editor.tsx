import type { RouteInfo } from "../../api/types";
import { vi } from "../../i18n/vi";
import { firstReal } from "../route-list-editor";

interface Props {
  route: RouteInfo | null;
  /** Provider names the crew actually built, so the list offers only what can answer. */
  providers: string[];
  readOnly: boolean;
  /** What holds the save, said under the row it is about. */
  error?: string;
  onChange: (next: RouteInfo | null) => void;
}

const ERROR_ID = "escalation-route-error";

/**
 * The one route a stuck turn moves to. Unlike the list above it, it may be left out
 * altogether, which is how every agent starts: a turn that is stuck then stops as it
 * always did. So the row is added and taken away whole, and there is never a second one.
 */
export function EscalationRouteEditor({ route, providers, readOnly, error, onChange }: Props) {
  const t = vi.editor;
  return (
    <div className="escalation-route" data-testid="escalation-route">
      <h4>{t.escalationRoute}</h4>
      <p className="muted">{t.escalationRouteHint}</p>
      {route === null ? (
        <>
          <p className="muted" data-testid="escalation-route-none">
            {t.escalationRouteNone}
          </p>
          <button
            type="button"
            className="ghost"
            disabled={readOnly}
            onClick={() => onChange({ provider: firstReal(providers), model: "" })}
          >
            {t.addEscalationRoute}
          </button>
        </>
      ) : (
        <>
          <div className="route-editor">
            <div className="row">
              <select
                aria-label={`${t.escalationRoute}: ${t.provider}`}
                value={route.provider}
                disabled={readOnly}
                onChange={(e) => onChange({ ...route, provider: e.target.value })}
              >
                {/* As in the list above: a provider the file names stays selectable even
                    when the crew did not build it, or an edit elsewhere would rewrite it. */}
                {[...new Set([...providers, route.provider])].map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
              <input
                type="text"
                aria-label={`${t.escalationRoute}: ${t.model}`}
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? ERROR_ID : undefined}
                value={route.model}
                disabled={readOnly}
                onChange={(e) => onChange({ ...route, model: e.target.value })}
              />
              <button type="button" className="ghost" disabled={readOnly} onClick={() => onChange(null)}>
                {t.removeEscalationRoute}
              </button>
            </div>
          </div>
          {error && (
            <span className="field-error" id={ERROR_ID} role="alert">
              {error}
            </span>
          )}
        </>
      )}
    </div>
  );
}
