import { useState } from "react";
import type { AgentInfo } from "../api/types";
import { useMemory } from "../hooks/use-memory";
import { vi } from "../i18n/vi";
import { MemoryAgentSection } from "./memory-agent-section";
import { MemoryProposalsSection } from "./memory-proposals-section";
import { MemorySearchSection } from "./memory-search-section";
import { MemoryUserSection } from "./memory-user-section";

type Section = "user" | "agents" | "search" | "proposals";

interface Props {
  agents: AgentInfo[];
  /** The agent the conversation is with; the person can look at another one here. */
  agentId: string;
  pendingProposals: number;
  agentName: (id: string) => string;
}

const SECTIONS: { id: Section; label: string }[] = [
  { id: "user", label: vi.memory.user },
  { id: "agents", label: vi.memory.agents },
  { id: "search", label: vi.memory.search },
  { id: "proposals", label: vi.memory.proposals },
];

/** Everything the crew remembers, in the same four scopes the agents read it in. */
export function MemoryPanel(props: Props) {
  const [section, setSection] = useState<Section>("user");
  const [agentId, setAgentId] = useState(props.agentId);
  const memory = useMemory(agentId, props.pendingProposals);

  return (
    <div data-testid="memory-panel">
      <div role="tablist" className="tabs sub">
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            type="button"
            role="tab"
            aria-selected={section === s.id}
            className={section === s.id ? "active" : ""}
            onClick={() => setSection(s.id)}
          >
            {s.label}
            {s.id === "proposals" && props.pendingProposals > 0 && (
              <span className="badge warn"> {props.pendingProposals}</span>
            )}
          </button>
        ))}
      </div>

      {section === "user" && (
        <MemoryUserSection
          user={memory.user}
          loadedAt={memory.loadedAt}
          onSaveUserMd={memory.saveUserMd}
          onSaveFact={memory.saveFact}
          onRemoveFact={memory.removeFact}
        />
      )}
      {section === "agents" && (
        <MemoryAgentSection
          agents={props.agents}
          agentId={agentId}
          memory={memory.agentMemory}
          onSelectAgent={setAgentId}
          onSaveMemory={memory.saveAgentMemory}
          onReadNote={memory.readNote}
          onSaveNote={memory.saveNote}
          onConsolidate={memory.consolidate}
        />
      )}
      {section === "search" && (
        <MemorySearchSection
          hits={memory.hits}
          agentName={props.agentName}
          onSearch={memory.search}
        />
      )}
      {section === "proposals" && (
        <MemoryProposalsSection
          proposals={memory.proposals}
          agentMemoryMd={memory.agentMemory?.memory_md ?? ""}
          agentName={props.agentName}
          onDecide={memory.decide}
          onUndo={memory.undo}
        />
      )}
    </div>
  );
}
