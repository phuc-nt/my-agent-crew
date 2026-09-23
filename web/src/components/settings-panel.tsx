import type { AgentInfo, SettingsInfo } from "../api/types";
import type { ManageSection } from "../hooks/use-route";
import { vi } from "../i18n/vi";
import { formatUsd } from "./budget-indicator";
import { MetricCard, MetricRow } from "./ui/metric-card";

interface Props {
  settings: SettingsInfo | null;
  /** The crew as loaded: which agent does what, and who it can hand work to. */
  agents?: AgentInfo[];
  /** Absent when the panel is a section of the manage screen rather than a drawer. */
  onClose?: () => void;
  /** Jumps to the section where a summarised thing is actually changed. */
  onNavigate?: (section: ManageSection) => void;
}

/**
 * Machine configuration, read-only here, as a grid of summary cards: how the install is wired,
 * which models answer, which keys are present, who is on the crew, and what the tools and
 * skills are. Each card answers one question at a glance; where a thing is changed
 * elsewhere, the card says so with a link instead of repeating that section's list.
 */
export function SettingsPanel({ settings, agents = [], onClose, onNavigate }: Props) {
  const t = vi.settingsSections;
  const crew = [...agents].sort((a, b) => Number(b.is_master) - Number(a.is_master));
  const link = (section: ManageSection, label: string) =>
    onNavigate && (
      <button type="button" className="link-button card-link" onClick={() => onNavigate(section)}>
        {label}
      </button>
    );

  return (
    <aside className="settings-panel" role={onClose ? "dialog" : undefined} aria-label={vi.settings}>
      {/* The manage screen already titles the section; only the drawer needs its own. */}
      {onClose && (
        <header>
          <h2>{vi.settings}</h2>
          <button type="button" className="icon-button" aria-label={vi.close} onClick={onClose}>
            ×
          </button>
        </header>
      )}
      <div className="metric-grid">
        {!settings && <p className="muted">{vi.loadFailed}</p>}
        {settings && (
          <MetricCard title={t.system}>
            <dl className="metric-dl">
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
          </MetricCard>
        )}
        {/* The crew comes from its own endpoint, so a settings call that failed hides the
            machine's configuration and nothing else. Not the crew section's cards: this
            is about how each agent is wired — its mode, its tools, who it may hand work to. */}
        {crew.length > 0 && (
          <MetricCard title={t.crew}>
            <ul className="metric-list" data-testid="settings-crew-list">
              {crew.map((agent) => (
                <li key={agent.id}>
                  <MetricRow
                    label={
                      <>
                        <code>{agent.id}</code>
                        {agent.is_master && <span className="badge master">{vi.crew.master}</span>}
                        <span className="badge">
                          {agent.mode === "work" ? vi.modeWork : vi.modeAssistant}
                        </span>
                      </>
                    }
                    value={vi.toolCount.replace("{n}", String(agent.tools.length))}
                    sub={
                      agent.delegates.length > 0
                        ? `${vi.delegatesTo}: ${agent.delegates.join(", ")}`
                        : undefined
                    }
                    subTone="accent"
                  />
                </li>
              ))}
            </ul>
            {link("crew", t.openCrew)}
          </MetricCard>
        )}
        {settings && (
          <>
            <MetricCard title={t.routes}>
              <ol className="metric-list">
                {settings.routes.map((r, index) => (
                  <li key={`${r.provider}:${r.model}`}>
                    <MetricRow
                      label={
                        <code>
                          {r.provider}:{r.model}
                        </code>
                      }
                      value={
                        <span className={`badge${index === 0 ? " ok" : ""}`}>
                          {index === 0 ? t.primary : t.fallback}
                        </span>
                      }
                    />
                  </li>
                ))}
              </ol>
            </MetricCard>
            <MetricCard title={t.keys}>
              <ul className="metric-list">
                {Object.entries(settings.keys).map(([name, present]) => (
                  <li key={name}>
                    <MetricRow
                      label={<code>{name}</code>}
                      value={
                        <span className={`badge ${present ? "ok" : "warn"}`}>
                          {present ? vi.keyPresent : vi.keyMissing}
                        </span>
                      }
                    />
                  </li>
                ))}
              </ul>
              {link("connections", t.openConnections)}
            </MetricCard>
            <MetricCard title={t.tools}>
              <MetricRow
                icon="🔧"
                label={t.tools}
                hint={t.toolsHint}
                value={t.toolsSummary(
                  settings.tools.length,
                  settings.tools.filter((tool) => tool.requires_approval).length,
                )}
              />
              {link("tools", t.openTools)}
            </MetricCard>
            <MetricCard title={t.skills}>
              <ul className="metric-list">
                {settings.skills.map((skill) => (
                  <li key={skill.name} data-testid={`skill-${skill.name}`}>
                    <MetricRow
                      label={
                        <>
                          <code>{skill.name}</code>
                          {skill.always && <span className="badge ok">{vi.alwaysOn}</span>}
                          {skill.missing_bins && skill.missing_bins.length > 0 && (
                            <span className="badge warn">
                              {vi.missingBins(skill.missing_bins.join(", "))}
                            </span>
                          )}
                        </>
                      }
                      sub={
                        <>
                          {skill.description}
                          {skill.cli_help && <div>{vi.cliHelp(skill.cli_help)}</div>}
                        </>
                      }
                    />
                  </li>
                ))}
              </ul>
            </MetricCard>
          </>
        )}
      </div>
    </aside>
  );
}
