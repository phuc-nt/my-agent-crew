import type { ConnectionsInfo, CredentialGroup } from "../api/types";
import type { CredentialsController } from "../hooks/use-credentials";
import { vi } from "../i18n/vi";
import { CredentialAddForm } from "./credential-add-form";
import { CredentialRow } from "./credential-row";
import { GlobalRoutesEditor } from "./global-routes-editor";
import { MetricCard } from "./ui/metric-card";

interface Props {
  connections: ConnectionsInfo;
  credentials: CredentialsController;
  /** Reload the registry after the page changes the crew: new routes, a new provider. */
  onChanged: () => Promise<void> | void;
}

/**
 * What the crew talks to outside itself, one card per kind: model providers, the routes
 * tried in order, web search, Telegram, and whatever other variables skills read. Each
 * card carries the keys and hosts that kind needs, set and checked where they are used.
 *
 * Values go one way. A key is typed into a password field, saved to the env file and
 * applied to the running crew; the page is only ever told whether it is set.
 */
export function ConnectionsPanel({ connections, credentials, onChanged }: Props) {
  const t = vi.connectionsPage;
  const rows = (group: CredentialGroup) => {
    const items = credentials.info?.items.filter((item) => item.group === group) ?? [];
    if (items.length === 0) return null;
    return (
      <ul className="metric-list" data-testid={`credentials-${group}`}>
        {items.map((item) => (
          <CredentialRow key={item.name} item={item} credentials={credentials} />
        ))}
      </ul>
    );
  };
  const listNote =
    !credentials.info && <p className="muted">{credentials.error ?? t.loading}</p>;

  return (
    <div className="connections" data-testid="connections">
      {credentials.info && <p className="muted">{t.hint(credentials.info.file)}</p>}
      {listNote}

      <MetricCard title={t.providers}>
        <div className="row wrap" data-testid="providers">
          <span className="muted">{t.providersBuilt}:</span>
          {connections.providers.map((provider) => (
            <span key={provider.name} className="badge ok">
              {provider.name}
            </span>
          ))}
        </div>
        {rows("model")}
      </MetricCard>

      <MetricCard title={t.routes}>
        <p className="muted">{t.routesHint}</p>
        <GlobalRoutesEditor connections={connections} onSaved={onChanged} />
        <h4 className="connections-subtitle">{t.visionRoutes}</h4>
        {connections.vision_routes.length === 0 ? (
          <p className="muted">{t.noVisionRoutes}</p>
        ) : (
          <ol className="route-list" data-testid="vision-routes">
            {connections.vision_routes.map((route, i) => (
              <li key={`${route.provider}/${route.model}/${i}`}>
                <code>{route.provider}</code> <span className="muted">{route.model}</span>
              </li>
            ))}
          </ol>
        )}
      </MetricCard>

      <MetricCard title={t.search}>
        <div className="row wrap" data-testid="search-backends">
          <span className="muted">{t.searchOrder}:</span>
          {connections.search_backends.map((backend, i) => (
            <span key={backend} className={`badge${i === 0 ? " ok" : ""}`}>
              {i + 1}. {backend}
            </span>
          ))}
        </div>
        {rows("search")}
        <p className="muted">{t.searchHint}</p>
      </MetricCard>

      <MetricCard title={t.telegram}>
        {connections.telegram.length === 0 ? (
          <p className="muted">{t.noTelegram}</p>
        ) : (
          <>
            <ul className="key-list" data-testid="telegram-list">
              {connections.telegram.map((channel) => (
                <li key={channel.agent_id}>
                  <code>{channel.agent_id}</code>
                  <span className="muted">
                    → <code>{channel.token_env}</code>
                  </span>
                  <span className={`badge ${channel.configured ? "ok" : "warn"}`}>
                    {channel.configured ? t.configured : t.notConfigured}
                  </span>
                  {channel.ignored && <span className="badge warn">{t.ignored}</span>}
                </li>
              ))}
            </ul>
            {rows("telegram")}
            <p className="muted">{t.telegramHint}</p>
          </>
        )}
      </MetricCard>

      {credentials.info && (
        <MetricCard title={t.other}>
          <p className="muted">{t.otherHint}</p>
          {rows("other") ?? <p className="muted">{t.noOther}</p>}
          <CredentialAddForm credentials={credentials} />
        </MetricCard>
      )}
    </div>
  );
}
