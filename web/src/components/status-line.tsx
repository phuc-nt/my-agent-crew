import { vi } from "../i18n/vi";
import type { ThreadState } from "../state/thread-reducer";

interface Props {
  thread: ThreadState;
  connected: boolean;
  liveCount: number;
}

function threadText(thread: ThreadState): string {
  if (thread.pending) return vi.statusAwaiting;
  const running = [...thread.items].reverse().find((i) => i.kind === "tool" && i.status === "running");
  if (running && running.kind === "tool") return vi.statusTool(running.name);
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
