import type { RunInfo } from "../../api/types";
import { ApprovalHistory } from "../../components/approval-history";
import { AttentionCenter } from "../../components/attention-center";
import { EmptyState } from "../../components/empty-state";
import { RecentRunsLog } from "../../components/recent-runs-log";
import { RunReplay } from "../../components/run-replay";
import { RunGroupCard } from "../../components/run-timeline";
import { vi } from "../../i18n/vi";
import { runGroups } from "../../state/activity-reducer";
import type { ManageProps } from "./manage-props";

interface WatchParts {
  failed: RunInfo[];
  awaiting: RunInfo[];
  live: RunInfo[];
  recent: RunInfo[];
  parentTitle: (run: RunInfo) => string | null;
  reloadAfterRow: () => void;
  approvalsKey: string;
}

/** The pages for one run, the activity and the approvals, as the screen draws them. */
export function watchPages(
  props: ManageProps,
  { failed, awaiting, live, recent, parentTitle, reloadAfterRow, approvalsKey }: WatchParts,
) {
  return (
    <>
      {props.section === "activity" && props.replayRunId !== undefined && (
        <RunReplay
          runId={props.replayRunId}
          known={props.runs}
          agentName={props.agentName}
          onBack={() => props.onReplayRun(null)}
          backLabel={props.fromJob ? vi.jobRow.back : undefined}
          onOpenConversation={props.onOpenConversation}
        />
      )}
      {props.section === "activity" && props.replayRunId === undefined && (
        <>
          <AttentionCenter
            runs={failed}
            parentTitle={parentTitle}
            agentName={props.agentName}
            onOpenConversation={props.onOpenConversation}
            waitingElsewhere={awaiting.length}
            onOpenWaiting={() => props.onNavigate("approvals")}
          />
          <h3>{vi.liveNow}</h3>
          {live.length === 0 ? (
            <EmptyState icon="activity" says={vi.nothingLive} />
          ) : (
            runGroups(live).map((group) => (
              <RunGroupCard
                key={group.run.id}
                group={group}
                agentName={props.agentName}
                expanded
                onOpenConversation={props.onOpenConversation}
                onOpenRun={props.onReplayRun}
              />
            ))
          )}
          <h3>{vi.recentRuns}</h3>
          <RecentRunsLog
            streamed={recent}
            agents={props.agents}
            agentName={props.agentName}
            onOpenConversation={props.onOpenConversation}
            onOpenRun={props.onReplayRun}
            onBackToChat={props.onBackToChat}
          />
        </>
      )}
      {props.section === "approvals" && (
        <>
          {/* What waits comes first and is decided here; the ledger of what was
              decided before sits under it. */}
          <AttentionCenter
            runs={awaiting}
            inline
            parentTitle={parentTitle}
            agentName={props.agentName}
            onOpenConversation={props.onOpenConversation}
            onReload={reloadAfterRow}
            failedElsewhere={failed.length}
            onOpenFailed={() => props.onNavigate("activity")}
          />
          <h3>{vi.approvalHistory}</h3>
          <ApprovalHistory
            agentName={props.agentName}
            onOpenConversation={props.onOpenConversation}
            refreshKey={approvalsKey}
          />
        </>
      )}
    </>
  );
}
