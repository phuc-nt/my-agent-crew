import { useCallback, useEffect, useLayoutEffect, useRef, useState, type UIEvent } from "react";
import type { RunInfo } from "../api/types";
import { ConnectionNotice } from "../components/connection-notice";
import { ErrorBoundary } from "../components/error-boundary";
import { failingJobs } from "../components/job-last-run";
import { useCredentials } from "../hooks/use-credentials";
import { standing, useMcpServers } from "../hooks/use-mcp-servers";
import { useRegistry } from "../hooks/use-registry";
import type { ManageSection } from "../hooks/use-route";
import { vi } from "../i18n/vi";
import { waitingKey } from "../lib/run-progress";
import { parentConversationId } from "../state/activity-reducer";
import { crewPages } from "./manage/crew-pages";
import { LABELS, ManageNav } from "./manage/manage-nav";
import type { ManageProps } from "./manage/manage-props";
import { systemPages } from "./manage/system-pages";
import { watchPages } from "./manage/watch-pages";

export { NAV_GROUPS } from "./manage/manage-nav";

/**
 * Everything about the crew rather than about one conversation: what is running, what
 * needs a decision, who is on the team, the schedule, what was remembered and the bill.
 *
 * It is a screen of its own rather than a rail beside the chat, because none of it is
 * about the conversation you are in — keeping it next to the thread made the crew's
 * work and the conversation's work look like the same thing.
 */
export function ManageScreen(props: ManageProps) {
  const registry = useRegistry();
  const mcp = useMcpServers();
  const { refresh: refreshRegistry } = registry;
  const { keysChanged: mcpKeysChanged, crewChanged: mcpCrewChanged } = mcp;
  // A save on the connections page is applied to the crew that is running: the server builds
  // it again. A key can build a provider or a search backend, and with it a tool an agent
  // did not hold; the routes every agent falls back on are the routes of each agent that
  // names none. An agent's editor works from the crew this page holds, so the crew is read
  // again along with the registry, which shows what was built.
  const { onReloadCrew } = props;
  const rebuilt = useCallback(async () => {
    await Promise.all([refreshRegistry(), onReloadCrew()]);
  }, [refreshRegistry, onReloadCrew]);
  // A key can also bring up an MCP server whose header reads it: the list of servers says so.
  const keysChanged = useCallback(async () => {
    await Promise.all([rebuilt(), mcpKeysChanged()]);
  }, [rebuilt, mcpKeysChanged]);
  const credentials = useCredentials(keysChanged);
  // Who holds which tool changes on the other pages: an agent is edited, made or removed,
  // a server is signed out of or tried again. So the grid is read again each time it is
  // opened, and under the person's eyes when a server's tools change or a try of it ends
  // while it is open. The read the screen opens with is the registry's own.
  const onTools = props.section === "tools";
  const stand = standing(mcp.servers);
  const opened = useRef(false);
  useEffect(() => {
    if (!opened.current) opened.current = true;
    else if (onTools) void refreshRegistry();
  }, [onTools, stand, refreshRegistry]);
  // An agent that is written, made or removed changes who uses a server, which the list of
  // servers says on the connections page: it is read again along with the crew. So are the
  // jobs, since the scheduler takes up what the profile now says without a restart.
  const crewChanged = () => {
    void onReloadCrew();
    void mcpCrewChanged();
    void props.onReloadJobs();
  };
  const editing = props.agents.find((a) => a.id === props.editingAgentId) ?? null;
  const pendingProposals = props.stats?.pending_proposals ?? 0;
  const failing = failingJobs(props.jobs);
  const liveIds = new Set(props.liveRuns.map((r) => r.id));
  const recent = props.runs.filter((r) => !liveIds.has(r.id));
  const live = props.runs.filter((r) => liveIds.has(r.id));
  // A request waits on a decision and is settled on the approvals page; a failure or a
  // halt is read and dismissed with the rest of the activity. Counting them together
  // sent the person to Duyệt for an error with nothing to decide.
  const awaiting = props.attention.filter((r) => r.status === "awaiting_approval");
  const failed = props.attention.filter((r) => r.status !== "awaiting_approval");
  // The ledger lists settled requests, and a request settles as its run leaves the pause.
  // Its key changes with every sign of that here: a run ending, the requests waiting
  // changing, and a row below changing something on the server. A sum of the first two
  // stays put when a resume and its end land in one update; and a turn that stops again on
  // its next tool is the same run waiting once more, told apart only by what it waits on.
  const [rowReloads, setRowReloads] = useState(0);
  const finishedRuns = props.runs.filter((r) => r.finished_at !== null).length;
  const approvalsKey = `${finishedRuns}|${waitingKey(awaiting)}|${rowReloads}`;
  const reloadAfterRow = () => {
    setRowReloads((n) => n + 1);
    props.onReloadActivity?.();
  };
  const parentTitle = (run: RunInfo) => {
    const parent = parentConversationId(run);
    if (parent === null) return null;
    const owner = props.runs.find((r) => r.conversation_id === parent);
    return owner ? owner.title || props.agentName(owner.agent_id) : null;
  };

  // A paused run is still live, but it is waiting on a person rather than running: it is
  // counted on Duyệt, and counting it here too would call one request two things at once.
  const running = props.liveRuns.filter((r) => r.status === "running").length;

  // Brings the current section's entry into view. On a phone the sections are one row of
  // pills scrolled sideways, and arriving on a section whose pill sits past the edge would
  // leave the person with no sign of where they are. The counts come after the first paint
  // and widen the pills, and a browser does not hold a sideways scroll in place as they
  // grow, so the entry is brought back when one changes — unless the person has scrolled
  // it out of sight since: the row is theirs then, and snapping it back would slide the
  // pill they were reaching for from under their finger. "nearest" moves nothing that is
  // already visible, so neither the sidebar on a wide screen nor a pill in view jumps.
  const active = useRef<HTMLButtonElement>(null);
  const shown = useRef<{ section: ManageSection | null; inView: boolean }>({ section: null, inView: true });
  const counts = [running, failed.length, awaiting.length, pendingProposals, failing].join();
  useLayoutEffect(() => {
    if (shown.current.section === props.section && !shown.current.inView) return;
    active.current?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
    shown.current = { section: props.section, inView: true };
  }, [props.section, counts]);
  // Where the person's scrolling left the current entry. A scroll event does not bubble in
  // React, so the wide screen's column and the phone's row each report their own.
  const onNavScroll = (event: UIEvent<HTMLElement>) => {
    const pill = active.current?.getBoundingClientRect();
    if (!pill) return;
    const box = event.currentTarget.getBoundingClientRect();
    shown.current.inView =
      pill.left >= box.left - 1 && pill.right <= box.right + 1 && pill.top >= box.top - 1 && pill.bottom <= box.bottom + 1;
  };

  return (
    <div className="manage-layout" data-testid="manage-screen">
      <ManageNav
        section={props.section}
        onNavigate={props.onNavigate}
        onBackToChat={props.onBackToChat}
        active={active}
        onNavScroll={onNavScroll}
        running={running}
        failed={failed}
        awaiting={awaiting}
        pendingProposals={pendingProposals}
        failing={failing}
      />
      <main className="manage-body" aria-label={vi.manage.label}>
        <h2 className="manage-title">{LABELS[props.section]}</h2>
        {props.connection && <ConnectionNotice {...props.connection} />}
        {/* One boundary per page, keyed by it: a section that breaks leaves the nav
            standing, and choosing any other page is enough to leave the failure behind. */}
        <ErrorBoundary key={`${props.section}/${props.replayRunId ?? props.editingAgentId ?? ""}`}>
          {/* The pages are functions called here, not components: what they read is read in
              this render, outside the boundary, and each page keeps its place under it. */}
          {watchPages(props, { failed, awaiting, live, recent, parentTitle, reloadAfterRow, approvalsKey })}
          {crewPages(props, { editing, registry, mcp, crewChanged, pendingProposals })}
          {systemPages(props, { registry, credentials, mcp, rebuilt })}
        </ErrorBoundary>
      </main>
    </div>
  );
}
