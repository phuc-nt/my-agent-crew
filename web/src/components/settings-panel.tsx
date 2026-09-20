import type { SettingsInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { formatUsd } from "./budget-indicator";

interface Props {
  settings: SettingsInfo | null;
  onClose: () => void;
}

export function SettingsPanel({ settings, onClose }: Props) {
  const t = vi.settingsSections;
  return (
    <aside className="settings-panel" role="dialog" aria-label={vi.settings}>
      <header>
        <h2>{vi.settings}</h2>
        <button type="button" className="icon-button" aria-label={vi.close} onClick={onClose}>
          ×
        </button>
      </header>
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
