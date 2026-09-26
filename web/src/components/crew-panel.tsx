import { useState } from "react";
import type { AgentInfo, InstallResult, TemplateInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { AddAgentForm } from "./add-agent-form";
import { AgentAvatar } from "./ui/agent-avatar";
import { Icon } from "./ui/icon";

interface Props {
  agents: AgentInfo[];
  /** The agent the person talks to; null while the crew is still loading. */
  master: AgentInfo | null;
  /** Bundled profiles; the ones already in the crew are shown but not installable. */
  templates: TemplateInfo[];
  liveByAgent: Record<string, number>;
  onInstall: (template: string) => Promise<InstallResult>;
  /** Opens one agent's editor. */
  onEdit: (agentId: string) => void;
  /** Called after an agent is created, so the list picks it up. */
  onCreated: (agentId: string) => void;
}

type Notice = { kind: "ok"; text: string; restart: boolean } | { kind: "error"; text: string };

/**
 * The team behind the master: who is in it, what each member does, and the bundled
 * profiles that can join with one click. Installing writes the profile to the home
 * directory and the server picks it up at once; only schedules wait for a restart,
 * which the notice says.
 */
export function CrewPanel({
  agents,
  master,
  templates,
  liveByAgent,
  onInstall,
  onEdit,
  onCreated,
}: Props) {
  const [installing, setInstalling] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [adding, setAdding] = useState(false);
  const installed = new Set(agents.map((a) => a.id));
  const masterName = master?.name ?? vi.agent;
  const delegates = new Set(master?.delegates ?? []);
  const ordered = [...agents].sort((a, b) => Number(b.is_master) - Number(a.is_master));

  const install = async (template: string) => {
    setInstalling(template);
    setNotice(null);
    try {
      const result = await onInstall(template);
      setNotice({
        kind: "ok",
        text: vi.crew.installed(result.installed),
        restart: result.needs_restart,
      });
    } catch (e) {
      setNotice({ kind: "error", text: vi.crew.installFailed(e instanceof Error ? e.message : String(e)) });
    } finally {
      setInstalling(null);
    }
  };

  return (
    <div className="crew-panel">
      <div className="row">
        <p className="muted">{vi.crew.intro(masterName)}</p>
        <span className="spacer" />
        {!adding && (
          <button type="button" className="primary" onClick={() => setAdding(true)}>
            {vi.crew.add}
          </button>
        )}
      </div>
      {adding && (
        <AddAgentForm
          onCancel={() => setAdding(false)}
          onCreated={(id) => {
            setAdding(false);
            onCreated(id);
          }}
        />
      )}
      <ul className="tool-list crew-list" data-testid="crew-list">
        {ordered.map((agent) => (
          <li key={agent.id} className="crew-card" data-testid="crew-agent">
            <div className="crew-card-head">
              <AgentAvatar id={agent.id} name={agent.name} size="lg" />
              <div className="crew-card-name">
                <strong>{agent.name}</strong>
                <code>{agent.id}</code>
              </div>
              <button type="button" className="ghost crew-card-action" onClick={() => onEdit(agent.id)}>
                <Icon name="edit" />
                {vi.crew.edit}
              </button>
            </div>
            <div className="crew-card-badges">
              {agent.is_master && <span className="badge master">{vi.crew.master}</span>}
              <span className="badge">{agent.mode === "work" ? vi.modeWork : vi.modeAssistant}</span>
              {(liveByAgent[agent.id] ?? 0) > 0 && (
                <span className="badge live">{vi.runStatus.running}</span>
              )}
              {agent.telegram && <span className="badge">{vi.crew.telegram}</span>}
              {!agent.is_master && delegates.has(agent.id) && (
                <span className="badge ok">{vi.crew.delegatable}</span>
              )}
            </div>
            {agent.description && <p className="crew-card-text">{agent.description}</p>}
            <div className="crew-card-facts">
              <span>{vi.toolCount.replace("{n}", String(agent.tools.length))}</span>
              {agent.schedules.length > 0 && <span>{vi.agentSchedules(agent.schedules.length)}</span>}
              {agent.commands.length > 0 && (
                <span title={agent.commands.map((c) => `/${c.name} — ${c.description}`).join("\n")}>
                  {vi.agentCommands(agent.commands.length)}
                </span>
              )}
              {agent.hooks > 0 && <span>{vi.agentHooks(agent.hooks)}</span>}
            </div>
            {agent.kits.length > 0 && (
              <div className="muted kit-list">
                {vi.agentKits}: {agent.kits.map((kit) => <code key={kit}>{kit}</code>)}
              </div>
            )}
          </li>
        ))}
      </ul>

      {templates.length > 0 && (
        <>
          <h3>{vi.crew.templates}</h3>
          <p className="muted">{vi.crew.templatesHint}</p>
          {notice && (
            <div className={`notice ${notice.kind === "ok" ? "ok" : "error"}`} role="status">
              {notice.text}
              {notice.kind === "ok" && notice.restart && <div className="muted">{vi.crew.needsRestart}</div>}
            </div>
          )}
          <ul className="tool-list template-list" data-testid="template-list">
            {templates.map((template) => (
              <li key={template.id} className="crew-card" data-testid="template">
                <div className="crew-card-head">
                  <AgentAvatar id={template.id} name={template.name} size="lg" />
                  <div className="crew-card-name">
                    <strong>{template.name}</strong>
                    <code>{template.id}</code>
                  </div>
                  {installed.has(template.id) ? (
                    <span className="badge ok crew-card-action">
                      <Icon name="check" />
                      {vi.crew.alreadyInstalled}
                    </span>
                  ) : (
                    <button
                      type="button"
                      className="crew-card-action"
                      disabled={installing !== null}
                      onClick={() => void install(template.id)}
                    >
                      {installing === template.id ? <Icon name="spinner" className="spinning" /> : <Icon name="download" />}
                      {installing === template.id ? vi.crew.installing : vi.crew.install}
                    </button>
                  )}
                </div>
                <div className="crew-card-badges">
                  <span className="badge">{template.mode === "work" ? vi.modeWork : vi.modeAssistant}</span>
                </div>
                <p className="crew-card-text">{template.description}</p>
                {template.tools.length > 0 && (
                  <div className="crew-card-facts">
                    <span>{vi.toolCount.replace("{n}", String(template.tools.length))}</span>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
