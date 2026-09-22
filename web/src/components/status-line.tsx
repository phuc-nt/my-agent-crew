import { vi } from "../i18n/vi";
import type { ThreadState } from "../state/thread-reducer";

interface Props {
  thread: ThreadState;
  connected: boolean;
  liveCount: number;
}

function threadText(thread: ThreadState): string {
  if (thread.pending) return vi.statusAwaiting;
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
export function StatusLine({ thread, connected, liveCount }: Props) {
  return (
    <div className="status-line" role="status" aria-live="polite" data-testid="status-line">
      <span>{threadText(thread)}</span>
      <span className={`stream-state ${connected ? "on" : "off"}`}>
        {connected ? vi.streamConnected : vi.streamDisconnected}
        {liveCount > 0 && ` · ${vi.liveNow}: ${liveCount}`}
      </span>
    </div>
  );
}
