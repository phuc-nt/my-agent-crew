import { useEffect, useState } from "react";
import { api } from "./api/client";
import type { SettingsInfo, TemplateInfo } from "./api/types";
import { ErrorBoundary } from "./components/error-boundary";
import { useActivity } from "./hooks/use-activity";
import { useCrew } from "./hooks/use-agents";
import { useConversations } from "./hooks/use-conversations";
import { type ManageSection, useRoute } from "./hooks/use-route";
import { useThread } from "./hooks/use-thread";
import { ChatScreen } from "./screens/chat-screen";
import { ManageScreen } from "./screens/manage-screen";
import { liveRuns, needsAttention, sortedRuns } from "./state/activity-reducer";

/**
 * The data every screen shares, and which screen is showing.
 *
 * The hooks live here rather than inside a screen so that moving between chat and manage
 * does not tear down the activity stream and re-open it — a reconnect would lose the runs
 * that arrived in between, and the person would come back to a screen that had forgotten
 * what was happening.
 */
export function App() {
  const { route, navigate } = useRoute();
  const list = useConversations();
  const thread = useThread(list.activeId);
  const crew = useCrew();
  const activity = useActivity(true, list.applyUpdate);
  const [settings, setSettings] = useState<SettingsInfo | null>(null);
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);

  useEffect(() => {
    api.settings().then(setSettings, () => setSettings(null));
    api.templates().then(setTemplates, () => setTemplates([]));
  }, []);

  // The address bar is what a shared or bookmarked link carries, so it opens the
  // conversation rather than the other way round. Back and Forward land here too, which
  // is how they end up showing the conversation the person was reading.
  const { select } = list;
  const routedId = route.kind === "chat" ? route.conversationId : null;
  useEffect(() => {
    if (routedId) select(routedId);
  }, [routedId, select]);

  // Each finished run changes the bill, the job history and per-conversation spend.
  const runs = sortedRuns(activity.state);
  const finished = runs.filter((r) => r.finished_at !== null).length;
  const { refreshJobs, refreshStats } = crew;
  const { refresh: refreshList } = list;
  useEffect(() => {
    if (finished === 0) return;
    void refreshJobs();
    void refreshStats();
    void refreshList();
  }, [finished, refreshJobs, refreshStats, refreshList]);

  const live = liveRuns(activity.state);
  const attention = needsAttention(activity.state);
  const liveByAgent: Record<string, number> = {};
  for (const run of live) liveByAgent[run.agent_id] = (liveByAgent[run.agent_id] ?? 0) + 1;

  const active =
    list.conversations.find((c) => c.id === list.activeId) ??
    (thread.detail && thread.detail.id === list.activeId ? thread.detail : null);

  // Opening a conversation from the manage screen does both things at once: the chat has
  // to be showing for the conversation to be worth selecting.
  const openConversation = (conversationId: string) => {
    list.select(conversationId);
    navigate({ kind: "chat", conversationId });
  };

  if (route.kind === "manage") {
    return (
      <ErrorBoundary>
        <ManageScreen
          section={route.section}
          runs={runs}
          liveRuns={live}
          attention={attention}
          jobs={crew.jobs}
          stats={crew.stats}
          settings={settings}
          agents={crew.agents}
          agentId={active?.agent_id ?? crew.master?.id ?? "default"}
          agentName={crew.agentName}
          master={crew.master}
          templates={templates}
          liveByAgent={liveByAgent}
          onInstall={crew.installTemplate}
          editingAgentId={route.agentId}
          onEditAgent={(agentId) =>
            navigate(
              agentId
                ? { kind: "manage", section: "crew", agentId }
                : { kind: "manage", section: "crew" },
            )
          }
          onReloadCrew={() => void crew.reload()}
          // Changing section drops the agent in the URL: an id is only meaningful under
          // the section that opened it.
          onNavigate={(section: ManageSection) => navigate({ kind: "manage", section })}
          onBackToChat={() => navigate({ kind: "chat", conversationId: list.activeId })}
          onOpenConversation={openConversation}
          onRunJob={(id) => void crew.runJob(id)}
          onToggleJob={(id, enabled) => void crew.setJobEnabled(id, enabled)}
        />
      </ErrorBoundary>
    );
  }

  return (
    <ChatScreen
      list={list}
      thread={thread}
      crew={crew}
      activity={activity}
      settings={settings}
      attentionCount={attention.length}
      onSelectConversation={openConversation}
      onOpenManage={(section = "activity") => navigate({ kind: "manage", section })}
      liveByAgent={liveByAgent}
    />
  );
}
