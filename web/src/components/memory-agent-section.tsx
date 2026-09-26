import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api/client";
import type { AgentInfo, AgentMemory, RunInfo } from "../api/types";
import { type RunStart, useStartedRun } from "../hooks/use-started-run";
import { vi } from "../i18n/vi";
import { MemoryEditor } from "./memory-editor";
import { RunChip, runOutcome } from "./run-chip";

interface Props {
  agents: AgentInfo[];
  agentId: string;
  memory: AgentMemory | null;
  onSelectAgent: (id: string) => void;
  onSaveMemory: (text: string) => Promise<void>;
  onReadNote: (day: string) => Promise<string>;
  onSaveNote: (day: string, body: string) => Promise<void>;
  onConsolidate: () => Promise<RunStart>;
  /** Every run the activity stream knows, to follow the consolidation started from here. */
  runs: RunInfo[];
  /** Re-reads what a finished consolidation may have changed. */
  onConsolidated: () => void;
}

/** One agent's own memory: the file it re-reads each turn, plus its dated notes. */
export function MemoryAgentSection(props: Props) {
  const [day, setDay] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [consolidating, setConsolidating] = useState(false);
  const [message, setMessage] = useState("");

  const { onConsolidate, onConsolidated } = props;
  const onSettled = useCallback(
    (run: RunInfo) => {
      setMessage(runOutcome(run));
      onConsolidated();
    },
    [onConsolidated],
  );
  const started = useStartedRun(props.runs, onSettled);
  const tracking = started.tracking && started.agentId === props.agentId;

  const consolidate = async () => {
    setConsolidating(true);
    setMessage("");
    try {
      await started.start(onConsolidate);
    } catch (error) {
      // 409 means one is already running; anything else is a plain failure.
      const busy = error instanceof ApiError && error.status === 409;
      setMessage(busy ? vi.memory.consolidateBusy : vi.memory.consolidateFailed);
    } finally {
      setConsolidating(false);
    }
  };

  const { onReadNote } = props;
  useEffect(() => {
    if (day === null) return;
    onReadNote(day).then(setNote, () => setNote(""));
  }, [day, onReadNote]);

  useEffect(() => {
    setDay(null);
  }, [props.agentId]);

  return (
    <div data-testid="memory-agent">
      <label>
        {vi.agents}
        <select value={props.agentId} onChange={(event) => props.onSelectAgent(event.currentTarget.value)}>
          {props.agents.map((agent) => (
            <option key={agent.id} value={agent.id}>
              {agent.name}
            </option>
          ))}
        </select>
      </label>

      {!props.memory ? (
        <p className="muted">{vi.loadFailed}</p>
      ) : (
        <>
          <MemoryEditor
            label={vi.memory.agentMemory}
            value={props.memory.memory_md}
            onSave={props.onSaveMemory}
          />
          <button
            type="button"
            disabled={consolidating || tracking}
            title={vi.memory.consolidateHint}
            onClick={() => void consolidate()}
          >
            {vi.memory.consolidate}
          </button>
          {tracking ? (
            <RunChip label={vi.memory.consolidateStarted} run={started.run} />
          ) : (
            message && <p className="muted">{message}</p>
          )}

          <h3>{vi.memory.notes}</h3>
          {props.memory.notes.length === 0 ? (
            <p className="muted">{vi.memory.notesEmpty}</p>
          ) : (
            <ul className="note-list">
              {props.memory.notes.map((n) => (
                <li key={n.day}>
                  <button
                    type="button"
                    className="ghost"
                    aria-pressed={day === n.day}
                    onClick={() => setDay(n.day)}
                  >
                    {n.day}
                  </button>
                  <span className="muted"> {vi.stepChars(n.chars)}</span>
                </li>
              ))}
            </ul>
          )}
          {day !== null && (
            <MemoryEditor
              label={`${vi.memory.noteBody} — ${day}`}
              value={note}
              rows={8}
              onSave={(text) => props.onSaveNote(day, text)}
            />
          )}
        </>
      )}
    </div>
  );
}
