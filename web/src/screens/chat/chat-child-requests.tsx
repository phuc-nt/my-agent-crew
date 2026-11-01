import type { RunInfo } from "../../api/types";
import { AttentionCenter } from "../../components/attention-center";
import { vi } from "../../i18n/vi";
import { waitingInDelegated } from "../../state/delegated-requests";
import { parentConversationId } from "../../state/run-groups";
import type { ChatProps } from "./chat-props";

interface Parts extends Pick<ChatProps, "crew" | "activity" | "onSelectConversation" | "waiting"> {
  runs: RunInfo[];
  conversationId: string | null;
}

/**
 * What the agents this conversation handed work to are waiting on, decided in place.
 *
 * A delegated child asks in its own conversation, and the open chat shows only its delegate
 * call still going: without this the person had to go to Duyệt or open the child's thread to
 * let the work go on. Deciding here takes the same routes; the child resumes, and the turn
 * that delegated to it goes on by itself.
 */
export function chatChildRequests({ crew, activity, onSelectConversation, waiting, runs, conversationId }: Parts) {
  if (!conversationId) return null;
  const asking = waitingInDelegated(runs, waiting, conversationId);
  // Under a grandchild, the child it works for: "Pong" alone would not say which of the
  // tasks handed out is the one asking.
  const parentTitle = (run: RunInfo) => {
    const parent = parentConversationId(run);
    if (parent === null || parent === conversationId) return null;
    const owner = runs.find((r) => r.conversation_id === parent);
    return owner ? owner.title || crew.agentName(owner.agent_id) : null;
  };
  return (
    <AttentionCenter
      // Rows held while a decision resumes belong to the conversation they were listed under.
      key={conversationId}
      runs={asking}
      inline
      hideWhenCalm
      heading={vi.attentionDelegated}
      className="child-requests"
      parentTitle={parentTitle}
      agentName={crew.agentName}
      onOpenConversation={onSelectConversation}
      onReload={() => void activity.refresh()}
    />
  );
}
