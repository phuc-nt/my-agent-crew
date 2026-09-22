// The editing state behind the agent editor: what the profile was, what it is in the
// form, and the difference between them — which is exactly what gets sent.
//
// Sending the difference rather than the whole profile is what lets a hand-written
// `agent.yaml` survive being edited from a browser. The server round-trips the file and
// only rewrites the keys it is given, so a key this version of the UI does not know
// about stays where its author put it, comment and all.
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { AgentInfo, AgentPatch } from "../api/types";

/** The keys the form can change. `id`, `dir` and everything derived stay out of it. */
export type DraftKey = keyof AgentPatch;

const EDITABLE: DraftKey[] = [
  "name",
  "description",
  "mode",
  "workspace",
  "routes",
  "cost_cap_usd",
  "max_steps",
  "autonomous",
  "shell_ask_patterns",
  "tool_output_chars",
  "memory_consolidate",
  "delegates",
  "tools",
  "schedules",
  "telegram",
];

export interface AgentDraft {
  /** The profile as the server last reported it; the baseline every diff is taken from. */
  original: AgentInfo | null;
  draft: AgentPatch;
  /** Which keys the person actually changed. Empty means there is nothing to save. */
  dirty: DraftKey[];
  saving: boolean;
  error: string | null;
  /** Why the crew has to be restarted for the last save to fully take effect. */
  restartRequired: string[];
  set: <K extends DraftKey>(key: K, value: AgentPatch[K]) => void;
  reset: () => void;
  save: () => Promise<boolean>;
}

/** Deep equality by serialisation: the values here are JSON already, and a route list or
 * a tool allow-list has to compare by content rather than by identity. */
function same(a: unknown, b: unknown): boolean {
  return JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
}

function toDraft(agent: AgentInfo): AgentPatch {
  return {
    name: agent.name,
    description: agent.description,
    mode: agent.mode,
    workspace: agent.workspace,
    routes: agent.routes,
    cost_cap_usd: agent.cost_cap_usd,
    max_steps: agent.max_steps,
    autonomous: agent.autonomous,
    shell_ask_patterns: agent.shell_ask_patterns,
    tool_output_chars: agent.tool_output_chars,
    memory_consolidate: agent.memory_consolidate,
    delegates: agent.delegates,
    tools: agent.tools,
    schedules: agent.schedules,
    telegram: agent.telegram,
  };
}

/**
 * One agent's editing session.
 *
 * `agent` is passed in rather than fetched so the editor shows the same profile the crew
 * list does — one source, no second request that can disagree with it. `onSaved` hands
 * the updated profile back so the list refreshes without a round trip.
 */
export function useAgentDraft(
  agent: AgentInfo | null,
  onSaved?: (profile: AgentInfo) => void,
): AgentDraft {
  const [original, setOriginal] = useState<AgentInfo | null>(agent);
  const [draft, setDraft] = useState<AgentPatch>(() => (agent ? toDraft(agent) : {}));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [restartRequired, setRestartRequired] = useState<string[]>([]);

  // A different agent means a different form. Reloading the same one mid-edit would
  // throw away what the person typed, so the id is the trigger, not the object.
  useEffect(() => {
    setOriginal(agent);
    setDraft(agent ? toDraft(agent) : {});
    setError(null);
    setRestartRequired([]);
  }, [agent?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const dirty = useMemo(() => {
    if (!original) return [];
    const base = toDraft(original);
    return EDITABLE.filter((key) => !same(draft[key], base[key]));
  }, [draft, original]);

  const set = useCallback(<K extends DraftKey>(key: K, value: AgentPatch[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
  }, []);

  const reset = useCallback(() => {
    setDraft(original ? toDraft(original) : {});
    setError(null);
  }, [original]);

  const save = useCallback(async () => {
    if (!original || dirty.length === 0) return true;
    setSaving(true);
    setError(null);
    try {
      const patch: AgentPatch = {};
      for (const key of dirty) Object.assign(patch, { [key]: draft[key] });
      const saved = await api.patchAgent(original.id, patch);
      setOriginal(saved.profile);
      setDraft(toDraft(saved.profile));
      setRestartRequired(saved.restart_required);
      onSaved?.(saved.profile);
      return true;
    } catch (e) {
      // The draft is deliberately left alone: a refused edit is usually one bad field
      // among several good ones, and clearing the form would make the person retype all
      // of them to find out which.
      setError(e instanceof Error ? e.message : String(e));
      return false;
    } finally {
      setSaving(false);
    }
  }, [dirty, draft, onSaved, original]);

  return { original, draft, dirty, saving, error, restartRequired, set, reset, save };
}
