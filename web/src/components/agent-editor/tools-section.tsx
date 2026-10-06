import type { McpServerInfo, McpStatus, RegistryTool } from "../../api/types";
import type { AgentDraft } from "../../hooks/use-agent-draft";
import { vi } from "../../i18n/vi";

interface Props {
  form: AgentDraft;
  readOnly: boolean;
  tools: RegistryTool[];
  mcpServers: McpServerInfo[];
}

const STATUS_TONE: Record<McpStatus, string> = { connected: "ok", idle: "warn", signed_out: "warn", failed: "danger" };

/**
 * Which tools the agent may use.
 *
 * An empty list is not "no tools" — it is "no allow-list", which means every tool the
 * mode grants. That difference is invisible in a bare set of checkboxes, so it gets its
 * own radio pair above them; ticking nothing would otherwise silently mean the opposite
 * of what it looks like.
 *
 * The tools of an MCP server are not in that list, and neither is the search that finds
 * them. They come with the server, which is switched on below, so the picker leaves them
 * out: ticking one would promise a say the allow-list does not have.
 */
export function ToolsSection({ form, readOnly, tools, mcpServers }: Props) {
  const own = tools.filter((tool) => !tool.server && !tool.with_mcp);
  const picked = form.draft.tools ?? [];
  const restricted = picked.length > 0;
  const servers = form.draft.mcp ?? [];
  // A name the file no longer declares keeps its row: the server refuses every save that
  // still carries it, and a row is the only thing a person can untick.
  const gone = servers.filter((name) => !mcpServers.some((server) => server.name === name));

  const toggle = (name: string) => {
    const next = picked.includes(name) ? picked.filter((t) => t !== name) : [...picked, name];
    form.set("tools", next);
  };
  const toggleServer = (name: string) =>
    form.set("mcp", servers.includes(name) ? servers.filter((s) => s !== name) : [...servers, name]);

  return (
    <section className="editor-section" data-testid="section-tools">
      <h3>{vi.editor.sectionTools}</h3>
      <div className="field check-field">
        <label>
          <input
            type="radio"
            name="tools-mode"
            checked={!restricted}
            disabled={readOnly}
            onChange={() => form.set("tools", [])}
          />
          <span>{vi.editor.toolsAll}</span>
        </label>
        <label>
          <input
            type="radio"
            name="tools-mode"
            checked={restricted}
            disabled={readOnly}
            // Switching on the allow-list with nothing ticked would save as "no
            // allow-list" again, so it starts from everything the agent holds today.
            onChange={() => form.set("tools", own.map((t) => t.name))}
          />
          <span>{vi.editor.toolsPick}</span>
        </label>
        <span className="muted field-hint">{vi.editor.toolsHint}</span>
      </div>
      <ul className="tool-picker" data-testid="tool-picker">
        {own.map((tool) => (
          <li key={tool.name}>
            <label>
              <input
                type="checkbox"
                checked={picked.includes(tool.name)}
                disabled={readOnly || !restricted}
                onChange={() => toggle(tool.name)}
              />
              <code>{tool.name}</code>
              {tool.optional && <span className="badge">{vi.tools.optional}</span>}
            </label>
            <div className="muted">{tool.description}</div>
          </li>
        ))}
      </ul>

      <h3>{vi.editor.mcp}</h3>
      <p className="muted">{vi.editor.mcpHint}</p>
      {mcpServers.length === 0 && gone.length === 0 ? (
        <p className="muted">{vi.editor.mcpNone}</p>
      ) : (
        <ul className="tool-picker" data-testid="mcp-picker">
          {mcpServers.map((server) => (
            <li key={server.name}>
              <label>
                <input
                  type="checkbox"
                  checked={servers.includes(server.name)}
                  disabled={readOnly}
                  onChange={() => toggleServer(server.name)}
                />
                <code>{server.name}</code>
                <span className={`badge ${STATUS_TONE[server.status]}`}>{vi.mcp.status[server.status]}</span>
              </label>
              <div className="muted">{server.description || server.url}</div>
              {server.tools.length > 0 && <div className="muted">{vi.mcp.tools(server.tools.length)}</div>}
            </li>
          ))}
          {gone.map((name) => (
            <li key={name}>
              <label>
                <input type="checkbox" checked disabled={readOnly} onChange={() => toggleServer(name)} />
                <code>{name}</code>
              </label>
              <div className="warn-text">{vi.editor.mcpGone}</div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
