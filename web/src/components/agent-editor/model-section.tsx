import type { AgentDraft } from "../../hooks/use-agent-draft";
import { vi } from "../../i18n/vi";
import { RouteListEditor } from "../route-list-editor";
import { EscalationRouteEditor } from "./escalation-route-editor";

interface Props {
  form: AgentDraft;
  readOnly: boolean;
  /** Provider names the crew actually built, so the list offers only what can answer. */
  providers: string[];
}

/**
 * The models the agent tries, in order — the second route only runs when the first one
 * fails — and under them the one a stuck turn moves to, if the agent names one. Saved with
 * the rest of the agent's profile.
 */
export function ModelSection({ form, readOnly, providers }: Props) {
  return (
    <section className="editor-section" data-testid="section-model">
      <h3>{vi.editor.sectionModel}</h3>
      <p className="muted">{vi.editor.routesHint}</p>
      <RouteListEditor
        routes={form.draft.routes ?? []}
        providers={providers}
        readOnly={readOnly}
        onChange={(next) => form.set("routes", next)}
      />
      <EscalationRouteEditor
        route={form.draft.escalation_route ?? null}
        providers={providers}
        readOnly={readOnly}
        error={form.problems.escalationRoute}
        onChange={(next) => form.set("escalation_route", next)}
      />
    </section>
  );
}
