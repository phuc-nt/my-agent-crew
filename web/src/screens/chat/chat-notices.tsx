import type { Conversation } from "../../api/types";
import { RaiseCapButton } from "../../components/budget-indicator";
import { Icon, type IconName } from "../../components/ui/icon";
import type { ForkController } from "../../hooks/use-fork";
import { vi } from "../../i18n/vi";
import { runSummaryText } from "../../lib/run-summary";
import type { ConversationMoney } from "../../state/conversation-money";
import type { ThreadState } from "../../state/thread-reducer";
import type { ChatProps } from "./chat-props";

const NOTICE_ICON: Record<string, IconName> = {
  fallback: "refresh",
  escalated: "arrow-up",
  halted: "pause",
  stopped: "stop",
  handled: "info",
  elsewhere: "info",
};

interface NoticeParts {
  state: ThreadState;
  money: ConversationMoney | null;
  active: Conversation | null;
  overBudget: boolean;
  raiseFromNotice: (cost_cap_usd: number) => Promise<void>;
}

/** What the last turn left to say: a change of route, a halt, a stop, an error. */
export function chatNotice({ state, money, active, overBudget, raiseFromNotice }: NoticeParts) {
  return state.notice && (
    <div className={`notice ${state.notice.kind}`} role="status" data-testid="notice">
      <Icon name={NOTICE_ICON[state.notice.kind] ?? "alert"} />
      {state.notice.kind === "halted"
        ? state.notice.text === "budget"
          ? overBudget || money?.capReached
            ? vi.haltedBudget
            : vi.haltedBudgetLifted
          : runSummaryText({ status: "halted", summary: state.notice.text })
        : state.notice.kind === "fallback"
          ? vi.routeFallback(state.notice.text)
          : state.notice.kind === "escalated"
            ? vi.routeEscalated(state.notice.reason ?? "error", state.notice.text)
            : state.notice.kind === "stopped"
              ? vi.stopped
              : state.notice.kind === "handled"
                ? vi.attentionHandled
                : state.notice.kind === "elsewhere"
                  ? vi.stopElsewhere
                  : vi.errorPrefix + state.notice.text}
      {state.notice.kind === "halted" && state.notice.text === "budget" && active && !overBudget && money?.capReached && (
        <RaiseCapButton capUsd={active.cost_cap_usd} onSave={raiseFromNotice} />
      )}
    </div>
  );
}

/** The conversations could not be read. */
export function loadFailedNotice(list: ChatProps["list"]) {
  return list.error && (
    <div className="notice error">
      <Icon name="alert" />
      {vi.loadFailed}
    </div>
  );
}

/** The last fork did not go through. */
export function forkErrorNotice(fork: ForkController) {
  return fork.error && (
    <div className="notice error" data-testid="fork-error">
      <Icon name="alert" />
      {fork.error}
    </div>
  );
}

/** The budget is spent, with the raise that lifts it. */
export function overBudgetNotice({ overBudget, active, raiseFromNotice }: Omit<NoticeParts, "state" | "money">) {
  return overBudget && active && (
    <div className="notice halted" data-testid="over-budget">
      <Icon name="coins" />
      {vi.overBudget}
      <RaiseCapButton capUsd={active.cost_cap_usd} onSave={raiseFromNotice} />
    </div>
  );
}
