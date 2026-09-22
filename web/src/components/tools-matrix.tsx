import type { AgentInfo, RegistryTool } from "../api/types";
import { vi } from "../i18n/vi";

interface Props {
  tools: RegistryTool[];
  agents: AgentInfo[];
}

/** Why an agent does or does not hold a tool. The four cases are genuinely different
 * problems: two are the person's own choice, one needs a key, one needs a mode change. */
type Cell = "on" | "excluded" | "missing-key" | "work-mode";

const MARK: Record<Cell, string> = {
  on: "✓",
  excluded: "–",
  "missing-key": "○",
  "work-mode": "▫",
};

const TITLE: Record<Cell, string> = {
  on: vi.tools.legendOn,
  excluded: vi.tools.legendExcluded,
  "missing-key": vi.tools.legendMissingKey,
  "work-mode": vi.tools.legendWorkMode,
};

/**
 * Read one cell.
 *
 * `tool.agents` is the ground truth — it comes from the toolboxes the server actually
 * built — so a hit is always a plain yes. A miss has to be explained, and the order
 * matters: an agent that excluded a tool by name never gets as far as needing its key.
 */
function cellFor(tool: RegistryTool, agent: AgentInfo): Cell {
  if (tool.agents.includes(agent.id)) return "on";
  if (agent.tools.length > 0 && !agent.tools.includes(tool.name)) return "excluded";
  if (tool.optional) return "missing-key";
  return "work-mode";
}

function approval(tool: RegistryTool): string {
  if (!tool.requires_approval) return vi.tools.never;
  return vi.tools.whenNotAutonomous;
}

/**
 * Every tool in the crew against every agent.
 *
 * A per-agent list would answer "what can this one do"; the question people actually ask
 * is the other one — "who can touch the shell" — and only the grid answers that at a
 * glance.
 */
export function ToolsMatrix({ tools, agents }: Props) {
  const ordered = [...agents].sort((a, b) => Number(b.is_master) - Number(a.is_master));

  if (tools.length === 0) return <p className="muted">{vi.tools.empty}</p>;

  return (
    <div className="tools-matrix">
      <p className="muted">{vi.tools.hint}</p>
      <div className="matrix-scroll">
        <table className="matrix" data-testid="tools-matrix">
          <thead>
            <tr>
              <th scope="col">{vi.tools.name}</th>
              <th scope="col">{vi.tools.needsApproval}</th>
              {ordered.map((agent) => (
                <th key={agent.id} scope="col" title={agent.id}>
                  {agent.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tools.map((tool) => (
              <tr key={tool.name} data-testid="tool-row">
                <th scope="row">
                  <code>{tool.name}</code>
                  {tool.optional && <span className="badge">{vi.tools.optional}</span>}
                  <div className="muted">{tool.description}</div>
                </th>
                <td className="approval">{approval(tool)}</td>
                {ordered.map((agent) => {
                  const cell = cellFor(tool, agent);
                  return (
                    <td key={agent.id} className={`cell ${cell}`} title={TITLE[cell]}>
                      <span aria-label={TITLE[cell]}>{MARK[cell]}</span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <dl className="matrix-legend">
        <dt>{vi.tools.legend}</dt>
        {(Object.keys(MARK) as Cell[]).map((cell) => (
          <dd key={cell}>{TITLE[cell]}</dd>
        ))}
      </dl>
    </div>
  );
}
