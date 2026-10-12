// A run this tab streams is on screen event by event, so its end loads nothing: all but the
// conversation's spend, which only a turn's `done` and `halted` say. Outside the list no row
// brings it, so a turn of this tab's that ends any other way owes one load there.
import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import type { RunInfo } from "../api/types";
import { emptyActivity } from "../state/activity-reducer";
import { emptyThread } from "../state/thread-reducer";
import type { ActivityController } from "./use-activity";
import { useExternalRunRefresh } from "./use-external-run-refresh";
import type { ThreadController } from "./use-thread";

const going: RunInfo = {
  id: "r1", agent_id: "coach", conversation_id: "c1", source: "chat", title: "t", status: "running",
  started_at: "2026-09-19T08:00:00Z", finished_at: null, spent_usd: 0, unknown_cost_calls: 0, summary: "", steps: [],
};
const ended = (status: RunInfo["status"]): RunInfo => ({ ...going, status, finished_at: "2026-09-19T08:00:05Z" });

function thread(busy: boolean, reloadWhenIdle: () => void): ThreadController {
  return {
    state: { ...emptyThread, busy },
    detail: null,
    send: vitest.fn(),
    decide: vitest.fn(),
    answer: vitest.fn(),
    stop: vitest.fn(),
    watch: vitest.fn(async () => true),
    watching: false,
    reload: vitest.fn(async () => undefined),
    reloadWhenIdle,
    settle: vitest.fn(),
    mutePreviews: vitest.fn(),
    unowned: 0,
    stops: 0,
  };
}

function activity(runs: RunInfo[]): ActivityController {
  const byId = Object.fromEntries(runs.map((r) => [r.id, r]));
  return { state: { ...emptyActivity, runs: byId, connected: true, synced: true }, refresh: vitest.fn(async () => undefined), connecting: false, synced: true, reconnect: vitest.fn() };
}

/** The hook over a turn this tab starts: busy first, then its run seen going on the stream. */
function ownTurn(unlisted: boolean) {
  const reloadWhenIdle = vitest.fn();
  const props = (busy: boolean, runs: RunInfo[]) => ({ thread: thread(busy, reloadWhenIdle), activity: activity(runs) });
  const hook = renderHook(({ thread, activity }) => useExternalRunRefresh("c1", thread, activity, unlisted), {
    initialProps: props(false, []),
  });
  const move = (busy: boolean, runs: RunInfo[]) => hook.rerender(props(busy, runs));
  move(true, []);
  move(true, [going]);
  return { reloadWhenIdle, move };
}

describe("the end of a run this tab streams, in a conversation outside the list", () => {
  it.each<RunInfo["status"]>(["error", "awaiting_approval"])("owes one load when it ends as %s, which says nothing of the spend", (status) => {
    const { reloadWhenIdle, move } = ownTurn(true);
    expect(reloadWhenIdle).not.toHaveBeenCalled();

    move(false, [ended(status)]);

    expect(reloadWhenIdle).toHaveBeenCalledTimes(1);
  });

  it.each<RunInfo["status"]>(["done", "halted"])("owes none when it ends as %s: the turn's last event said the spend", (status) => {
    const { reloadWhenIdle, move } = ownTurn(true);

    move(false, [ended(status)]);

    expect(reloadWhenIdle).not.toHaveBeenCalled();
  });

  it("owes none while the run only goes on", () => {
    const { reloadWhenIdle, move } = ownTurn(true);

    move(true, [{ ...going, summary: "bước hai" }]);
    move(false, [going]);

    expect(reloadWhenIdle).not.toHaveBeenCalled();
  });

  // The run stays in what the stream holds, and the hook looks at it again on every turn.
  it("owes that load once, however often the ended run is looked at again", () => {
    const { reloadWhenIdle, move } = ownTurn(true);
    move(false, [ended("error")]);

    move(true, [ended("error")]);
    move(false, [ended("error")]);

    expect(reloadWhenIdle).toHaveBeenCalledTimes(1);
  });
});

describe("the end of a run this tab streams, in a listed conversation", () => {
  // The sidebar's row is read again when a run ends, and brings the spend with it.
  it.each<RunInfo["status"]>(["error", "awaiting_approval", "done", "halted"])("owes no load when it ends as %s", (status) => {
    const { reloadWhenIdle, move } = ownTurn(false);

    move(false, [ended(status)]);

    expect(reloadWhenIdle).not.toHaveBeenCalled();
  });
});
