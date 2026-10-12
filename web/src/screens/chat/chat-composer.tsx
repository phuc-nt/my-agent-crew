import type { Dispatch, SetStateAction } from "react";
import type { AgentInfo, Conversation, RunInfo } from "../../api/types";
import { ApprovalBar } from "../../components/approval-bar";
import { Composer, type RestoreRequest } from "../../components/composer";
import { QuestionCard } from "../../components/question-card";
import type { useSavingNote } from "../../hooks/use-saving-note";
import { vi } from "../../i18n/vi";
import type { ConversationMoney } from "../../state/conversation-money";
import type { ThreadState } from "../../state/thread-reducer";
import type { ChatProps } from "./chat-props";

interface PendingParts extends Pick<ChatProps, "thread" | "list"> {
  state: ThreadState;
}

/** The agent's question, with the box that answers it. */
export function chatQuestion({ state, thread }: Omit<PendingParts, "list">) {
  return state.pending?.kind === "question" && (
    <QuestionCard
      pending={state.pending}
      busy={state.busy}
      onAnswer={(text) => void thread.answer(text)}
    />
  );
}

/** A call waiting on the person's word. */
export function chatApproval({ state, thread, list }: PendingParts) {
  return state.pending && state.pending.kind !== "question" && (
    <ApprovalBar
      pending={state.pending}
      busy={state.busy}
      onDecide={(ok) => void thread.decide(ok)}
      // Withheld whenever a reason stopped the call: that pause cannot be waived (see
      // `tool_gate.needs_decision`), so always-allowing the tool here would not stop
      // this card coming back — it would only let the tool's other calls run unasked.
      // The header shows the always-allow list from the conversation list, so refresh it.
      onAlways={
        state.pending.reason ? undefined : () => void thread.decide(true, true).then(list.refresh)
      }
    />
  );
}

interface ComposerParts extends Pick<ChatProps, "list" | "crew"> {
  state: ThreadState;
  money: ConversationMoney | null;
  externalRun: RunInfo | null;
  stoppable: boolean;
  restore: RestoreRequest | null;
  saving: ReturnType<typeof useSavingNote>;
  draft: string | undefined;
  setDraft: Dispatch<SetStateAction<string | undefined>>;
  active: Conversation | null;
  master: AgentInfo | null;
  send: (text: string) => Promise<boolean>;
  onStop: () => Promise<void>;
}

/** Where the person writes, and stops what is under way. */
export function chatComposer({
  list,
  crew,
  state,
  money,
  externalRun,
  stoppable,
  restore,
  saving,
  draft,
  setDraft,
  active,
  master,
  send,
  onStop,
}: ComposerParts) {
  return (
    <Composer
      // Anything pending blocks the composer, question included: the server refuses a
      // new message while an approval waits, so an enabled box would only collect text
      // and then 409. The question card carries its own input for the reply. A spent
      // budget blocks it too: the server would halt the turn before it started.
      disabled={state.pending !== null || Boolean(money?.overBudget)}
      busy={state.busy || externalRun !== null}
      stoppable={stoppable}
      restore={restore}
      note={saving.shown ? vi.canvas.savingFirst : undefined}
      draft={draft}
      draftKey={list.activeId ?? "new"}
      agentName={active ? crew.agentName(active.agent_id) : master?.name}
      commands={(active ? crew.agents.find((a) => a.id === active.agent_id) : master)?.commands ?? []}
      onSend={(text) => {
        setDraft(undefined);
        return send(text);
      }}
      onStop={() => void onStop()}
    />
  );
}
