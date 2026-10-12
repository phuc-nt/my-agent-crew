import { useEffect, useId, useRef, useState } from "react";
import type { McpServerInfo, McpStatus, RegistryTool } from "../../api/types";
import type { AgentDraft } from "../../hooks/use-agent-draft";
import { vi } from "../../i18n/vi";
import { ScriptControls } from "./script-controls";
import { allowList } from "./tool-allow-list";

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
 * Which names a list has a say over is the server's to decide, and it says so for each
 * agent as it is saved (`listable_tools`): the picker offers a tick for those and for no
 * other. So the tools of an MCP server, the search that finds them and the script tool get
 * no row: they come with the server switched on below, or with what the agent may read,
 * whatever the list says.
 *
 * A name the list holds that the server does not report keeps a row of its own, ticked and
 * said to bring nothing, because only the person takes a name off a list: the form writes
 * exactly what is ticked. And since the rows follow the agent as saved, a change to its
 * mode or to whom it hands work is to be saved before the tools are chosen: a line under
 * the picker says so while the form holds one.
 *
 * Such a name has no row to stay in once it is unticked, which leaves a keyboard that was
 * on it nowhere. It goes to the row that took its place, else to the last row; and to
 * "every tool" when that was the last name, since an empty list is no list.
 */
export function ToolsSection({ form, readOnly, tools, mcpServers }: Props) {
  const strayMark = useId();
  const savedFirst = useId();
  const list = allowList(tools, form.original, form.draft);
  const own = list.rows;
  const picked = form.draft.tools ?? [];
  const restricted = picked.length > 0;
  const unsaved = form.dirty.includes("mode") || form.dirty.includes("delegates");
  const rows = useRef<HTMLUListElement>(null);
  const every = useRef<HTMLInputElement>(null);
  /** Where among the picker's boxes the row a person just unticked away stood. */
  const [left, setLeft] = useState<{ at: number } | null>(null);
  useEffect(() => {
    if (left === null || document.activeElement !== document.body) return;
    const boxes = rows.current?.querySelectorAll<HTMLInputElement>("input") ?? [];
    const next = boxes[Math.min(left.at, boxes.length - 1)];
    (next && !next.disabled ? next : every.current)?.focus();
  }, [left]);
  const servers = form.draft.mcp ?? [];
  // A name the file no longer declares keeps its row: the server refuses every save that
  // still carries it, and a row is the only thing a person can untick.
  const gone = servers.filter((name) => !mcpServers.some((server) => server.name === name));

  const toggle = (name: string) =>
    form.set("tools", picked.includes(name) ? picked.filter((t) => t !== name) : [...picked, name]);
  const toggleServer = (name: string) =>
    form.set("mcp", servers.includes(name) ? servers.filter((s) => s !== name) : [...servers, name]);

  return (
    <section className="editor-section" data-testid="section-tools">
      <h3>{vi.editor.sectionTools}</h3>
      <div className="field check-field">
        <label>
          <input
            ref={every}
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
            aria-describedby={unsaved ? savedFirst : undefined}
            // Switching on the allow-list with nothing ticked would save as "no
            // allow-list" again, so it starts from everything the agent holds today.
            onChange={() => form.set("tools", list.start)}
          />
          <span>{vi.editor.toolsPick}</span>
        </label>
        <span className="muted field-hint">{vi.editor.toolsHint}</span>
      </div>
      <ul className="tool-picker" data-testid="tool-picker" ref={rows}>
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
        {list.stray.map((name, at) => (
          <li key={name}>
            <label>
              <input
                type="checkbox"
                checked
                disabled={readOnly}
                aria-describedby={`${strayMark}-${at}`}
                onChange={() => {
                  toggle(name);
                  setLeft({ at: own.length + at });
                }}
              />
              <code>{name}</code>
            </label>
            <div className="warn-text" id={`${strayMark}-${at}`}>
              {vi.editor.toolNotGiven}
            </div>
          </li>
        ))}
      </ul>
      {unsaved && (
        <p className="warn-text field-hint" id={savedFirst}>
          {vi.editor.toolsFollowSaved}
        </p>
      )}

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

      <ScriptControls form={form} readOnly={readOnly} />
    </section>
  );
}
