import { useState } from "react";
import type { AgentInfo, SettingsInfo, TemplateInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { formatUsd } from "./budget-indicator";

interface Props {
  settings: SettingsInfo | null;
  /** The crew as loaded: which agent does what, and who it can hand work to. */
  agents?: AgentInfo[];
  /** Profiles shipped with the app, installable by command. */
  templates?: TemplateInfo[];
  onClose: () => void;
}

const INSTALL = "python -m my_agent_crew agent add";

/**
 * A template is installed by a command rather than a button: it writes into the home
 * directory, and the server only reads agent profiles at startup, so a click would
 * leave the page showing an agent that is not running yet.
 */
function TemplateRow({ template }: { template: TemplateInfo }) {
  const [copied, setCopied] = useState(false);
  const command = `${INSTALL} ${template.id}`;
  return (
    <li>
      <code>{template.id}</code>
      <span className="badge">{template.mode === "work" ? vi.modeWork : vi.modeAssistant}</span>
      <div className="muted">{template.description}</div>
      <div className="template-install">
        <code>{command}</code>
        <button
          type="button"
          className="link-button"
          onClick={() => {
            void navigator.clipboard?.writeText(command);
            setCopied(true);
          }}
        >
          {copied ? vi.copied : vi.copyCommand}
        </button>
      </div>
    </li>
  );
}

export function SettingsPanel({ settings, agents = [], templates = [], onClose }: Props) {
  const t = vi.settingsSections;
  return (
    <aside className="settings-panel" role="dialog" aria-label={vi.settings}>
      <header>
        <h2>{vi.settings}</h2>
        <button type="button" className="icon-button" aria-label={vi.close} onClick={onClose}>
          ×
        </button>
      </header>
      {/* The crew and the bundled profiles come from their own endpoints, so a settings
          call that failed hides the machine's configuration and nothing else. */}
      <div className="settings-body">
        {agents.length > 0 && (
          <>
            <h3>{t.crew}</h3>
            <ul className="tool-list agent-list" data-testid="crew-list">
              {agents.map((agent) => (
                <li key={agent.id}>
                  <code>{agent.id}</code>
                  <span className="badge">
                    {agent.mode === "work" ? vi.modeWork : vi.modeAssistant}
                  </span>
                  <span className="muted"> {vi.toolCount.replace("{n}", String(agent.tools.length))}</span>
                  {agent.delegates.length > 0 && (
                    <div className="muted">
                      {vi.delegatesTo}: {agent.delegates.join(", ")}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
        {templates.length > 0 && (
          <>
            <h3>{t.templates}</h3>
            <p className="muted">{vi.templatesHint}</p>
            <ul className="tool-list template-list" data-testid="template-list">
              {templates.map((template) => (
                <TemplateRow key={template.id} template={template} />
              ))}
            </ul>
          </>
        )}
      </div>
      {!settings ? (
        <p className="muted">{vi.loadFailed}</p>
      ) : (
        <div className="settings-body">
          <h3>{t.routes}</h3>
          <ol>
            {settings.routes.map((r) => (
              <li key={`${r.provider}:${r.model}`}>
                <code>
                  {r.provider}:{r.model}
                </code>
              </li>
            ))}
          </ol>
          <h3>{t.keys}</h3>
          <ul className="key-list">
            {Object.entries(settings.keys).map(([name, present]) => (
              <li key={name}>
                <code>{name}</code>
                <span className={`badge ${present ? "ok" : "warn"}`}>
                  {present ? vi.keyPresent : vi.keyMissing}
                </span>
              </li>
            ))}
          </ul>
          <h3>{t.tools}</h3>
          <ul className="tool-list">
            {settings.tools.map((tool) => (
              <li key={tool.name}>
                <code>{tool.name}</code>
                {tool.requires_approval && <span className="badge">{vi.requiresApproval}</span>}
                <div className="muted">{tool.description}</div>
              </li>
            ))}
          </ul>
          <h3>{t.skills}</h3>
          <ul className="tool-list">
            {settings.skills.map((skill) => (
              <li key={skill.name}>
                <code>{skill.name}</code>
                {skill.always && <span className="badge ok">{vi.alwaysOn}</span>}
                <div className="muted">{skill.description}</div>
              </li>
            ))}
          </ul>
          <h3>{t.paths}</h3>
          <dl className="path-list">
            <dt>{vi.home}</dt>
            <dd>
              <code>{settings.home}</code>
            </dd>
            <dt>{vi.workspace}</dt>
            <dd>
              <code>{settings.workspace_dir}</code>
            </dd>
            <dt>{vi.usersDir}</dt>
            <dd>
              <code>{settings.users_dir}</code>
            </dd>
            <dt>{vi.maxSteps}</dt>
            <dd>{settings.max_steps}</dd>
            <dt>{vi.defaultCap}</dt>
            <dd>{settings.cost_cap_usd > 0 ? formatUsd(settings.cost_cap_usd) : vi.unlimited}</dd>
          </dl>
        </div>
      )}
    </aside>
  );
}
