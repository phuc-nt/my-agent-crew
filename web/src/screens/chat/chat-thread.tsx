import type { Dispatch, SetStateAction } from "react";
import type { AgentInfo, Conversation, RunInfo } from "../../api/types";
import { ConversationActivity } from "../../components/conversation-activity";
import { ErrorBoundary } from "../../components/error-boundary";
import { MessageThread } from "../../components/message-thread";
import type { CanvasWriting } from "../../hooks/use-canvas-writing";
import type { ConversationMoney } from "../../state/conversation-money";
import type { ThreadItem, ThreadState } from "../../state/thread-reducer";
import type { ChatProps } from "./chat-props";
import type { useChatCanvas } from "./use-chat-canvas";

interface ThreadParts extends Pick<ChatProps, "crew" | "onSelectConversation"> {
  state: ThreadState;
  externalRun: RunInfo | null;
  activeRun: RunInfo | null;
  echoOnly: boolean;
  active: Conversation | null;
  canvasLinks: ReturnType<typeof useChatCanvas>["canvasLinks"];
  writing: CanvasWriting;
  setDraft: Dispatch<SetStateAction<string | undefined>>;
  master: AgentInfo | null;
  crewNames: string[];
  onFork: (item: ThreadItem) => void;
}

/** What was said, under a boundary of its own. */
export function chatThread({
  crew,
  onSelectConversation,
  state,
  externalRun,
  activeRun,
  echoOnly,
  active,
  canvasLinks,
  writing,
  setDraft,
  master,
  crewNames,
  onFork,
}: ThreadParts) {
  return (
    <ErrorBoundary>
      <MessageThread
        items={state.items}
        streaming={state.streaming}
        // A run started from another channel shows its progress the same way, so the
        // thread does not look idle while an answer is on its way.
        busy={state.busy || externalRun !== null}
        liveRun={activeRun}
        echoOnly={echoOnly}
        agentId={active?.agent_id ?? "default"}
        agentName={crew.agentName}
        onOpenConversation={onSelectConversation}
        canvas={canvasLinks}
        writing={{ items: writing.items, onShow: writing.show }}
        onSuggestion={(text) => setDraft(text)}
        masterName={master?.name}
        crewNames={crewNames}
        // A delegate's own conversation (`parent_call_id` set) is not a valid fork
        // source — the server rejects it with 400 — so the button is withheld there
        // rather than offering something that would only fail on click.
        onFork={active && !active.parent_call_id ? onFork : undefined}
      />
    </ErrorBoundary>
  );
}

interface ActivityParts extends Pick<ChatProps, "crew" | "onSelectConversation"> {
  active: Conversation | null;
  conversationRuns: RunInfo[];
  money: ConversationMoney | null;
  collapseSignal: number;
  docked: boolean;
}

/** The conversation's activity, one element that the screen puts under the thread or beside the canvas. */
export function chatActivityPane({
  crew,
  onSelectConversation,
  active,
  conversationRuns,
  money,
  collapseSignal,
  docked,
}: ActivityParts) {
  return active && (
    <ErrorBoundary>
      <ConversationActivity
        runs={conversationRuns}
        conversationId={active.id}
        spentUsd={money?.spentUsd ?? 0}
        capUsd={active.cost_cap_usd}
        agentName={crew.agentName}
        onOpenConversation={onSelectConversation}
        collapseSignal={collapseSignal}
        docked={docked}
      />
    </ErrorBoundary>
  );
}
