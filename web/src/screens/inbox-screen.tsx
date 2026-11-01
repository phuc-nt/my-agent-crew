import type { RunInfo } from "../api/types";
import { AttentionCenter } from "../components/attention-center";
import { InboxResults } from "../components/inbox-results";
import { Icon } from "../components/ui/icon";
import { useInbox } from "../hooks/use-inbox";
import { vi } from "../i18n/vi";
import { parentConversationId } from "../state/activity-reducer";

interface Props {
  /** Every run the activity stream holds, newest first. */
  runs: RunInfo[];
  /** What waits on the person: requests to settle, and failures not yet read. */
  attention: RunInfo[];
  agentName: (id: string) => string;
  onOpenConversation: (conversationId: string) => void;
  /** Opens a run that has no conversation of its own on its page. */
  onOpenRun: (runId: string) => void;
  onBack: () => void;
  onReload: () => void;
}

/**
 * The phone's way in, in place of a chat app's notifications: what waits on the person
 * first, settled where it is listed, then what the scheduled jobs reported.
 *
 * Anything harder than a decision or a read — editing a job, replaying a run step by step —
 * stays on the manage screen, which a phone can reach but is not shaped for.
 */
export function InboxScreen(props: Props) {
  const { runs, agentName, onOpenConversation } = props;
  const { results, fresh, loadFailed } = useInbox(runs);
  const parentTitle = (run: RunInfo) => {
    const parent = parentConversationId(run);
    if (parent === null) return null;
    const owner = runs.find((r) => r.conversation_id === parent);
    return owner ? owner.title || agentName(owner.agent_id) : null;
  };
  const open = (run: RunInfo) =>
    run.conversation_id ? onOpenConversation(run.conversation_id) : props.onOpenRun(run.id);

  return (
    <div className="inbox-layout" data-testid="inbox-screen">
      <header className="inbox-header">
        <button type="button" className="icon-button" aria-label={vi.inbox.back} onClick={props.onBack}>
          <Icon name="chevron-left" />
        </button>
        <h1>{vi.inbox.title}</h1>
      </header>
      <main className="inbox-body" aria-label={vi.inbox.title}>
        <AttentionCenter
          runs={props.attention}
          inline
          parentTitle={parentTitle}
          agentName={agentName}
          onOpenConversation={onOpenConversation}
          onReload={props.onReload}
        />
        {loadFailed && <p className="muted inbox-note">{vi.inbox.loadFailed}</p>}
        <InboxResults results={results} fresh={fresh} agentName={agentName} onOpen={open} />
      </main>
    </div>
  );
}
