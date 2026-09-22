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

/** The keys `mode: work` supplies a default for when the manifest stays silent. */
const MODE_DEFAULTED: DraftKey[] = ["cost_cap_usd", "max_steps", "autonomous"];

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

/**
 * The form's starting point.
 *
 * `delegates` and `schedules` come from `declared` rather than from the effective
 * profile: the master with no delegates of its own reaches every agent, and writing that
 * computed list back would pin it to today's crew, leaving agents added later
 * unreachable. The consolidation job is likewise generated from `memory_consolidate`,
 * and saving it as an ordinary schedule would run it twice.
 */
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
    delegates: agent.declared.delegates,
    tools: agent.tools,
    schedules: agent.declared.schedules,
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
    const changed = EDITABLE.filter((key) => !same(draft[key], base[key]));
    // The limits ride along with a mode change even when their values match the
    // baseline. A patch that omits them lets the new mode's defaults apply instead, and
    // those defaults are not what the form is showing.
    if (changed.includes("mode")) {
      for (const key of MODE_DEFAULTED) if (!changed.includes(key)) changed.push(key);
    }
    return changed;
  }, [draft, original]);

  // Changing the mode moves three limits behind the form's back: a work agent that does
  // not state them gets a wider budget, more steps and autonomy turned on. The fields
  // stay on screen showing the old numbers, so saving only `mode` would grant a 40x cost
  // cap and unattended running that nobody typed. Pinning the displayed values makes the
  // form honest — the person can then raise them deliberately.
  const set = useCallback(<K extends DraftKey>(key: K, value: AgentPatch[K]) => {
    setDraft((current) => {
      const next = { ...current, [key]: value };
      if (key === "mode" && value !== current.mode) {
        next.cost_cap_usd = current.cost_cap_usd;
        next.max_steps = current.max_steps;
        next.autonomous = current.autonomous;
      }
      return next;
    });
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
