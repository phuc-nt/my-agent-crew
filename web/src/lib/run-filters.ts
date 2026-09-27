// What the recent-runs log can be narrowed by, and how the choice is remembered.
//
// The agent is asked of the server (a quiet agent's runs sit behind a busy one's in any
// crew-wide page); status and source only narrow what has already been loaded, so they
// cost no request and cannot hide a run the page has not fetched.
import type { RunInfo } from "../api/types";
import { readJson, writeJson } from "./local-store";
import type { SettledStatus } from "./run-progress";

export interface RunFilters {
  agent: string | null;
  status: SettledStatus | null;
  /** A source kind from `sourceKind`, not a raw source. */
  source: string | null;
}

export const NO_FILTERS: RunFilters = { agent: null, status: null, source: null };

/** The log shows finished runs only; what is still going sits in its own list above. */
export const FILTER_STATUSES: readonly SettledStatus[] = ["done", "error", "halted"];

// The first part of a run's source names where it came from: "chat" is the web page,
// "job:coach/brief" a schedule, "memory:wiki" a memory job, "delegate:<id>" a hand-off.
const KIND_BY_PREFIX: Record<string, string> = {
  chat: "web",
  telegram: "telegram",
  job: "schedule",
  delegate: "delegate",
  memory: "memory",
  api: "api",
};
const KIND_ORDER = ["web", "telegram", "schedule", "delegate", "memory", "api"];

/** Where a run came from, as one of a few kinds; an unknown source keeps its own prefix. */
export function sourceKind(source: string): string {
  const prefix = source.split(":")[0];
  return KIND_BY_PREFIX[prefix] ?? prefix;
}

/** The kinds worth offering: those present, plus the chosen one so it can be undone. */
export function sourceKinds(runs: RunInfo[], chosen: string | null): string[] {
  const present = new Set(runs.map((run) => sourceKind(run.source)));
  if (chosen) present.add(chosen);
  const rank = (kind: string) => (KIND_ORDER.includes(kind) ? KIND_ORDER.indexOf(kind) : KIND_ORDER.length);
  return [...present].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

export function filterRuns(runs: RunInfo[], filters: RunFilters): RunInfo[] {
  return runs.filter(
    (run) =>
      (filters.agent === null || run.agent_id === filters.agent) &&
      (filters.status === null || run.status === filters.status) &&
      (filters.source === null || sourceKind(run.source) === filters.source),
  );
}

// Namespaced to the log, so another view's filters never read this one's.
const FILTERS_KEY = "activity-log.filters";

/** The viewer's last choice; a browser that refuses storage starts unfiltered. */
export function readFilters(): RunFilters {
  const saved = readJson(FILTERS_KEY) as Record<string, unknown> | null;
  if (!saved || typeof saved !== "object") return NO_FILTERS;
  const text = (value: unknown) => (typeof value === "string" && value ? value : null);
  const status = FILTER_STATUSES.find((s) => s === saved.status) ?? null;
  return { agent: text(saved.agent), status, source: text(saved.source) };
}

/** Remembering is a convenience; where storage is refused the filters still work for this visit. */
export function writeFilters(filters: RunFilters): void {
  writeJson(FILTERS_KEY, filters);
}
