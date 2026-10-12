import type { RunInfo, SettingsInfo } from "../../api/types";
import type { useActivity } from "../../hooks/use-activity";
import type { useCrew } from "../../hooks/use-agents";
import type { useConversations } from "../../hooks/use-conversations";
import type { ManageSection } from "../../hooks/use-route";
import type { useThread } from "../../hooks/use-thread";

export interface ChatProps {
  list: ReturnType<typeof useConversations>;
  thread: ReturnType<typeof useThread>;
  crew: ReturnType<typeof useCrew>;
  activity: ReturnType<typeof useActivity>;
  settings: SettingsInfo | null;
  /** How many runs across the crew are waiting on a person; opens the manage screen. */
  attentionCount: number;
  /** Selects a conversation and puts it in the address bar, so the link can be shared. */
  onSelectConversation: (conversationId: string) => void;
  onOpenManage: (section?: ManageSection) => void;
  liveByAgent: Record<string, number>;
  /** A run for this conversation that another channel started, while this tab streams nothing. */
  externalRun?: RunInfo | null;
}
