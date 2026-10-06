import type { AgentInfo, RegistryTool } from "../api/types";
import { vi } from "../i18n/vi";

interface Props {
  tools: RegistryTool[];
  agents: AgentInfo[];
}

/** Why an agent does or does not hold a tool. The cases are genuinely different
 * problems: two are the person's own choice, one needs a key, one needs a mode change,
 * a tool of an MCP server comes with the server or not at all, and the two tools that
 * come with such tools (the search for them, the script that calls them) are held only
 * while one of them needs it. */
type Cell = "on" | "excluded" | "missing-key" | "work-mode" | "mcp-off" | "mcp-none";

const MARK: Record<Cell, string> = {
  on: "✓",
  excluded: "–",
  "missing-key": "○",
  "work-mode": "▫",
  "mcp-off": "◇",
  "mcp-none": "·",
};

const TITLE: Record<Cell, string> = {
  on: vi.tools.legendOn,
  excluded: vi.tools.legendExcluded,
  "missing-key": vi.tools.legendMissingKey,
  "work-mode": vi.tools.legendWorkMode,
  "mcp-off": vi.tools.legendMcpOff,
  "mcp-none": vi.tools.legendMcpNone,
};

/** A mark only some crews can meet, and the tools that bring it. */
const ONLY_WITH: Partial<Record<Cell, (tool: RegistryTool) => boolean>> = {
  "mcp-off": (tool) => Boolean(tool.server),
  "mcp-none": (tool) => Boolean(tool.with_mcp),
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
  // The allow-list, the keys and the mode have no say over a server's tools: an agent
  // holds them once the server is switched on for it, so that is the one thing to name.
  if (tool.server) return "mcp-off";
  // Nor over the search for them or the script that calls them: each is missing only
  // where no tool of a server needs it.
  if (tool.with_mcp) return "mcp-none";
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
  // A mark nobody can meet is not worth a line of legend.
  const legend = (Object.keys(MARK) as Cell[]).filter((cell) => {
    const brings = ONLY_WITH[cell];
    return !brings || tools.some(brings);
  });

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
                  {tool.server && <span className="badge">{vi.tools.fromServer(tool.server)}</span>}
                  {tool.with_mcp && (
                    <span className="badge" title={vi.tools.withMcpTitle}>
                      {vi.tools.withMcp}
                    </span>
                  )}
                  {tool.exposure && (
                    <span className="badge" title={vi.mcp.exposureTitle[tool.exposure]}>
                      {vi.mcp.exposure[tool.exposure]}
                    </span>
                  )}
                  {/* Held to two lines so the grid stays a grid; the whole text is on hover. */}
                  <div className="muted tool-description" title={tool.description}>
                    {tool.description}
                  </div>
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
        {legend.map((cell) => (
          <dd key={cell}>
            <span className={`legend-mark ${cell}`} aria-hidden="true">
              {MARK[cell]}
            </span>
            {TITLE[cell]}
          </dd>
        ))}
      </dl>
    </div>
  );
}
