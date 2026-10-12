import type { AgentInfo, Conversation, InstallResult, JobInfo, SettingsInfo, StatsInfo, TemplateInfo } from "../../api/types";
import type { RunInfo } from "../../api/types";
import type { ManageSection } from "../../hooks/use-route";

export interface ManageProps {
  section: ManageSection;
  runs: RunInfo[];
  liveRuns: RunInfo[];
  attention: RunInfo[];
  jobs: JobInfo[] | null;
  stats: StatsInfo | null;
  settings: SettingsInfo | null;
  /** The build this page runs and the one the server runs, shown under Settings. */
  versions?: { page: string | null; server: string | null };
  agents: AgentInfo[];
  agentId: string;
  agentName: (id: string) => string;
  master: AgentInfo | null;
  templates: TemplateInfo[];
  liveByAgent: Record<string, number>;
  onInstall: (template: string) => Promise<InstallResult>;
  /** The agent whose editor is open, when the URL names one. */
  editingAgentId?: string;
  /** The run shown on its own, when the URL names one. */
  replayRunId?: string;
  /** Opens or closes the editor by rewriting the route, so Back leaves it. */
  onEditAgent: (agentId: string | null) => void;
  /** Opens or closes a single run by rewriting the route, so Back leaves it. */
  onReplayRun: (runId: string | null, fromJob?: string) => void;
  /** Re-reads the crew after a profile is written, created or removed, and after a save on
   *  the connections page, which the server answers by building the crew again. */
  onReloadCrew: () => Promise<void> | void;
  /** Re-reads the jobs list after a profile is written, created or removed: a saved
   *  schedule is live at once, and that list is where its row and next run show. */
  onReloadJobs: () => Promise<void> | void;
  onNavigate: (section: ManageSection) => void;
  /** Reads the activity list again after a request was settled from the approvals page. */
  onReloadActivity?: () => void;
  /** Leaving the manage screen: back to the chat, opening a conversation if one is named. */
  onBackToChat: () => void;
  onOpenConversation: (conversationId: string) => void;
  onRunJob: (jobId: string) => void;
  onToggleJob: (jobId: string, enabled: boolean) => void;
  onDeleteJob: (jobId: string) => void;
  /** The part of the open editor to bring into view, when the URL names one. */
  editFocus?: string;
  /** Opens an agent's editor on its schedules, from a row in the jobs list. */
  onEditSchedules?: (agentId: string, fromJob: string) => void;
  /** The row of the jobs list to bring into view, when the URL names one. */
  focusJob?: string;
  /** What the URL names under the canvas section; the section decides whether it is a canvas's id. */
  canvasId?: string;
  /** Opens a canvas on its own page, or the library for none, by rewriting the route. */
  onOpenCanvas: (canvasId: string | null) => void;
  /** The conversations this tab has listed, for the names of those a canvas is used in. */
  conversations: Conversation[];
  /** The job whose row the open editor or run was reached from: its back link returns there. */
  fromJob?: string;
  /** The live stream the pages follow; absent leaves out the notice of a drop. */
  connection?: { connected: boolean; connecting: boolean; onRetry: () => void };
}
