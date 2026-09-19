import type { AgentInfo } from "../api/types";
import { vi } from "../i18n/vi";

interface Props {
  agents: AgentInfo[];
  selectedId: string | null;
  liveByAgent: Record<string, number>;
  onSelect: (id: string | null) => void;
}

/** Sidebar top: pick which agent's conversations to show and which one new chats go to. */
export function AgentSwitcher({ agents, selectedId, liveByAgent, onSelect }: Props) {
  if (agents.length <= 1) return null;
  return (
    <div className="agent-switcher" role="radiogroup" aria-label={vi.agents}>
      <button
        type="button"
        role="radio"
        aria-checked={selectedId === null}
        className={`agent-item ${selectedId === null ? "active" : ""}`}
        onClick={() => onSelect(null)}
      >
        {vi.allAgents}
      </button>
      {agents.map((agent) => (
        <button
          key={agent.id}
          type="button"
          role="radio"
          aria-checked={selectedId === agent.id}
          className={`agent-item ${selectedId === agent.id ? "active" : ""}`}
          title={agent.description || agent.workspace}
          onClick={() => onSelect(agent.id)}
        >
          <span className="agent-name">{agent.name}</span>
          {liveByAgent[agent.id] > 0 && <span className="badge live">{liveByAgent[agent.id]}</span>}
          {agent.schedules.length > 0 && (
            <span className="muted agent-meta">{vi.agentSchedules(agent.schedules.length)}</span>
          )}
        </button>
      ))}
    </div>
  );
}
