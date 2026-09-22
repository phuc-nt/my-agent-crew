import type { AgentInfo, SettingsInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { formatUsd } from "./budget-indicator";

interface Props {
  settings: SettingsInfo | null;
  /** The crew as loaded: which agent does what, and who it can hand work to. */
  agents?: AgentInfo[];
  /** Absent when the panel is a section of the manage screen rather than a drawer. */
  onClose?: () => void;
}

/** Machine configuration, read-only. Installing templates lives in the crew tab. */
export function SettingsPanel({ settings, agents = [], onClose }: Props) {
  const t = vi.settingsSections;
  const crew = [...agents].sort((a, b) => Number(b.is_master) - Number(a.is_master));
  return (
    <aside className="settings-panel" role={onClose ? "dialog" : undefined} aria-label={vi.settings}>
      <header>
        <h2>{vi.settings}</h2>
        {onClose && (
          <button type="button" className="icon-button" aria-label={vi.close} onClick={onClose}>
            ×
          </button>
        )}
      </header>
      {/* The crew comes from its own endpoint, so a settings call that failed hides the
          machine's configuration and nothing else. */}
      <div className="settings-body">
        {crew.length > 0 && (
          <>
            <h3>{t.crew}</h3>
            {/* Not the crew section's list: this one is about how each agent is wired —
                its mode, its tools, who it may hand work to. */}
            <ul className="tool-list agent-list" data-testid="settings-crew-list">
              {crew.map((agent) => (
                <li key={agent.id}>
                  <code>{agent.id}</code>
                  {agent.is_master && <span className="badge master">{vi.crew.master}</span>}
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
              <li key={skill.name} data-testid={`skill-${skill.name}`}>
                <code>{skill.name}</code>
                {skill.always && <span className="badge ok">{vi.alwaysOn}</span>}
                {skill.missing_bins && skill.missing_bins.length > 0 && (
                  <span className="badge warn">
                    {vi.missingBins(skill.missing_bins.join(", "))}
                  </span>
                )}
                <div className="muted">{skill.description}</div>
                {skill.cli_help && <div className="muted">{vi.cliHelp(skill.cli_help)}</div>}
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
            <dt>{vi.timezone}</dt>
            <dd>
              <code>{settings.zone}</code>
              {settings.timezone ? "" : ` (${vi.machineZone})`}
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
