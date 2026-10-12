import { useCallback, useState } from "react";
import type { AgentInfo, RunInfo } from "../api/types";
import { useMemory } from "../hooks/use-memory";
import { useRoute } from "../hooks/use-route";
import { vi } from "../i18n/vi";
import { MemoryAgentSection } from "./memory-agent-section";
import { MemoryProposalsSection } from "./memory-proposals-section";
import { MemorySearchSection } from "./memory-search-section";
import { MemoryUserSection } from "./memory-user-section";
import { ScriptStoreSection } from "./script-store-section";
import { WikiSection } from "./wiki-section";

type Section = "user" | "agents" | "wiki" | "scripts" | "search" | "proposals";

/** What the address says after `#/manage/memory/` when it opens the script store, with the
 *  agent's id after it: a namespace's owner is found from a job or a run, so the screen
 *  that shows what its scripts keep is one a link can name. */
const SCRIPTS_PARAM = "scripts";

interface Props {
  agents: AgentInfo[];
  /** The agent the conversation is with; the person can look at another one here. */
  agentId: string;
  pendingProposals: number;
  agentName: (id: string) => string;
  /** The activity stream's runs, so a compile or consolidation started here can be followed. */
  runs: RunInfo[];
}

const SECTIONS: { id: Section; label: string }[] = [
  { id: "user", label: vi.memory.user },
  { id: "agents", label: vi.memory.agents },
  { id: "wiki", label: vi.wiki.tab },
  { id: "scripts", label: vi.scriptStore.tab },
  { id: "search", label: vi.memory.search },
  { id: "proposals", label: vi.memory.proposals },
];

/** Everything the crew remembers, in the same four scopes the agents read it in. */
export function MemoryPanel(props: Props) {
  const [chosen, setSection] = useState<Section>("user");
  const [agentId, setAgentId] = useState(props.agentId);
  const { route, navigate } = useRoute();
  // The script store is the one tab the address names; the others live in the panel alone.
  const linked = route.kind === "manage" && route.section === "memory" && route.param === SCRIPTS_PARAM ? route : null;
  const section: Section = linked ? "scripts" : chosen;
  // An agent the address names is the one shown while the crew has it; the crew may not
  // have been read yet, and a name is not turned away before it has.
  const named = linked?.focus;
  const storeAgentId = named && (props.agents.length === 0 || props.agents.some((a) => a.id === named)) ? named : agentId;
  const openStore = (id: string) => navigate({ kind: "manage", section: "memory", param: SCRIPTS_PARAM, focus: id });
  const open = (next: Section) => {
    if (next === "scripts") return openStore(storeAgentId);
    setSection(next);
    if (!linked) return;
    // Leaving the store by a tab: the agent looked at there is the one the next tab shows.
    setAgentId(storeAgentId);
    navigate({ kind: "manage", section: "memory" });
  };
  const memory = useMemory(agentId, props.pendingProposals);
  const { refreshAgent, refreshProposals } = memory;
  // A consolidation proposes a rewrite and may have written notes; both are re-read.
  const onConsolidated = useCallback(() => {
    void refreshAgent().catch(() => undefined);
    void refreshProposals().catch(() => undefined);
  }, [refreshAgent, refreshProposals]);

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
            onClick={() => open(s.id)}
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
          runs={props.runs}
          onConsolidated={onConsolidated}
        />
      )}
      {section === "wiki" && (
        <WikiSection
          agents={props.agents}
          agentId={agentId}
          runs={props.runs}
          onSelectAgent={setAgentId}
          onReadNote={memory.readNote}
          onSaveNote={memory.saveNote}
        />
      )}
      {section === "scripts" && (
        <ScriptStoreSection agents={props.agents} agentId={storeAgentId} onSelectAgent={openStore} />
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
          agentId={agentId}
          agentMemoryMd={memory.agentMemory?.memory_md ?? ""}
          facts={memory.user?.facts ?? null}
          agentName={props.agentName}
          onDecide={memory.decide}
          onUndo={memory.undo}
          onRefresh={memory.refreshProposals}
        />
      )}
    </div>
  );
}
