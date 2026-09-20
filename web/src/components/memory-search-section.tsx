import { useState } from "react";
import type { MemoryHit } from "../api/types";
import { vi } from "../i18n/vi";

interface Props {
  hits: MemoryHit[] | null;
  agentName: (id: string) => string;
  onSearch: (query: string, onlyThisAgent: boolean) => Promise<void>;
}

/** One box across every scope: the shared facts and each agent's own files. */
export function MemorySearchSection({ hits, agentName, onSearch }: Props) {
  const [query, setQuery] = useState("");
  const [onlyThisAgent, setOnlyThisAgent] = useState(false);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    void onSearch(query, onlyThisAgent);
  };

  return (
    <div data-testid="memory-search">
      <form onSubmit={submit}>
        <label>
          {vi.memory.search}
          <input
            value={query}
            placeholder={vi.memory.searchPlaceholder}
            onChange={(event) => setQuery(event.currentTarget.value)}
          />
        </label>
        <label className="toggle">
          <input
            type="checkbox"
            checked={onlyThisAgent}
            onChange={(event) => setOnlyThisAgent(event.currentTarget.checked)}
          />
          {onlyThisAgent ? vi.memory.scopeAgent : vi.memory.scopeAll}
        </label>
        <button type="submit">{vi.memory.search}</button>
      </form>

      {hits !== null &&
        (hits.length === 0 ? (
          <p className="muted">{vi.memory.searchEmpty}</p>
        ) : (
          <ul className="hit-list">
            {hits.map((hit, index) => (
              <li key={`${hit.scope}-${hit.agent_id}-${hit.file}-${index}`}>
                <span className="badge">
                  {hit.scope === "user" ? vi.memory.scopeUser : agentName(hit.agent_id)}
                </span>
                <code>{hit.file}</code>
                <div>{hit.text}</div>
              </li>
            ))}
          </ul>
        ))}
    </div>
  );
}
