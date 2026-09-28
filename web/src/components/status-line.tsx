import { useOnline } from "../hooks/use-online";
import { vi } from "../i18n/vi";
import type { ThreadState } from "../state/thread-reducer";

interface Props {
  thread: ThreadState;
  connected: boolean;
  liveCount: number;
  /** The stream was just (re)opened: not yet live, but not lost either. */
  connecting?: boolean;
  /** Re-opens the activity stream; absent hides the retry. */
  onReconnect?: () => void;
  /** The conversation's budget is spent, so nothing can be sent until the cap is raised. */
  overBudget?: boolean;
}

function threadText(thread: ThreadState, overBudget: boolean): string {
  if (thread.pending) return vi.statusAwaiting;
  // The composer above is locked, so an idle line would claim a readiness it lacks.
  if (overBudget && !thread.busy) return vi.statusOverBudget;
  // Thinking is always the newest thing happening, so it outranks an earlier note.
  if (thread.busy && thread.thinking) return vi.statusThinking;
  // The newest of either kind wins, so the line follows the turn rather than preferring
  // one sort of item. A note that came after the tool call it introduces would otherwise
  // be shadowed by it, and a note is the better status text: the agent wrote it to be
  // read here, where a tool name is only the name of a mechanism.
  const latest = [...thread.items]
    .reverse()
    .find((i) => i.kind === "note" || (i.kind === "tool" && i.status === "running"));
  if (latest?.kind === "note") return latest.text;
  if (latest?.kind === "tool") return vi.statusTool(latest.name);
  if (thread.busy) return vi.statusStreaming;
  return vi.statusIdle;
}

/** Screen-reader friendly one-liner: what this thread is doing and whether live activity is flowing. */
export function StatusLine({ thread, connected, liveCount, connecting = false, onReconnect, overBudget = false }: Props) {
  const online = useOnline();
  const [state, text] = !online
    ? ["offline", vi.streamOffline]
    : connected
      ? ["on", vi.streamConnected]
      : connecting
        ? ["connecting", vi.streamConnecting]
        : ["off", vi.streamDisconnected];
  return (
    <div className="status-line" role="status" aria-live="polite" data-testid="status-line">
      <span>{threadText(thread, overBudget)}</span>
      <span className={`stream-state ${state}`} data-testid="stream-state">
        {text}
        {liveCount > 0 && ` · ${vi.liveNow}: ${liveCount}`}
        {state === "off" && onReconnect && (
          <button
            type="button"
            className="link-button stream-retry"
            aria-label={vi.streamRetryLabel}
            onClick={onReconnect}
          >
            {vi.retry}
          </button>
        )}
      </span>
    </div>
  );
}
