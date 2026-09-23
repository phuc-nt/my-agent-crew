import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ConnectionsInfo, RouteInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { RouteListEditor } from "./route-list-editor";

interface Props {
  connections: ConnectionsInfo;
  /** Reload what the page shows after a save: the routes the server kept, and whatever
   * the rebuilt crew now reports. */
  onSaved: () => Promise<void> | void;
}

type Note = { tone: "ok" | "warn" | "danger"; text: string };

const same = (a: RouteInfo[], b: RouteInfo[]) =>
  a.length === b.length && a.every((r, i) => r.provider === b[i].provider && r.model === b[i].model);

/**
 * The routes every agent falls back on, edited in place. The server tries the list
 * before keeping it, so a provider with no key or a list the crew cannot run with comes
 * back as a note and nothing is written. While MY_AGENT_ROUTES decides them the list is
 * shown read-only: a save to config.yaml would be hidden by the variable.
 *
 * When the saved routes change (a save, or a reload after a key change) the draft starts
 * again from what the server kept; the note from the save stays.
 */
export function GlobalRoutesEditor({ connections, onSaved }: Props) {
  const t = vi.connectionsPage;
  const [draft, setDraft] = useState<RouteInfo[]>(connections.routes);
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState<Note | null>(null);
  const readOnly = connections.routes_source === "env";
  const changed = !same(draft, connections.routes);
  const providers = connections.providers.map((p) => p.name);
  const savedKey = JSON.stringify(connections.routes);

  useEffect(() => {
    setDraft(JSON.parse(savedKey) as RouteInfo[]);
  }, [savedKey]);

  const save = async () => {
    setSaving(true);
    setNote(null);
    try {
      const answer = await api.setRoutes(
        draft.map((r) => ({ provider: r.provider, model: r.model.trim() })),
      );
      setNote(
        answer.restart_required
          ? { tone: "warn", text: answer.restart_required }
          : { tone: "ok", text: t.routesSaved },
      );
      await onSaved();
    } catch (e) {
      setNote({ tone: "danger", text: t.failed(e instanceof Error ? e.message : String(e)) });
    } finally {
      setSaving(false);
    }
  };

  const source = {
    env: t.routesSourceEnv,
    config: t.routesSourceConfig,
    default: t.routesSourceDefault,
  }[connections.routes_source];

  return (
    <div className="global-routes" data-testid="routes">
      <RouteListEditor
        routes={draft}
        providers={providers}
        readOnly={readOnly || saving}
        onChange={(next) => {
          setDraft(next);
          setNote(null);
        }}
        testId="global-route-editor"
      />
      <p className={readOnly ? "credential-note warn" : "muted"} data-testid="routes-source">
        {source}
      </p>
      {!readOnly && (
        <div className="row">
          <button
            type="button"
            disabled={!changed || saving || draft.some((r) => !r.model.trim())}
            onClick={() => void save()}
          >
            {saving ? t.saving : t.routesSave}
          </button>
          <button
            type="button"
            className="ghost"
            disabled={!changed || saving}
            onClick={() => {
              setDraft(connections.routes);
              setNote(null);
            }}
          >
            {t.routesReset}
          </button>
        </div>
      )}
      {note && (
        <p className={`credential-note ${note.tone}`} role="status">
          {note.text}
        </p>
      )}
    </div>
  );
}
