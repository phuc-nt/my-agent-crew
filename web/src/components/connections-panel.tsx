import type { ConnectionsInfo } from "../api/types";
import { vi } from "../i18n/vi";

interface Props {
  connections: ConnectionsInfo;
}

/**
 * What the crew talks to outside itself: the providers it built, the model routes it
 * tries in order, the API keys it found, and the Telegram channels.
 *
 * Everything here is read-only by design. A key is shown by the name of its environment
 * variable and whether a value was found — never the value, and there is no field to type
 * one into, because a secret typed into a browser would end up in the request log, the
 * profile file and the person's password manager all at once.
 */
export function ConnectionsPanel({ connections }: Props) {
  return (
    <div className="connections" data-testid="connections">
      <p className="muted">{vi.connectionsPage.hint}</p>

      <section>
        <h3>{vi.connectionsPage.providers}</h3>
        <div className="row wrap" data-testid="providers">
          {connections.providers.map((provider) => (
            <span key={provider.name} className="badge ok">
              {provider.name}
            </span>
          ))}
        </div>
      </section>

      <section>
        <h3>{vi.connectionsPage.routes}</h3>
        <ol className="route-list" data-testid="routes">
          {connections.routes.map((route, i) => (
            <li key={`${route.provider}/${route.model}/${i}`}>
              <code>{route.provider}</code> <span className="muted">{route.model}</span>
            </li>
          ))}
        </ol>
      </section>

      <section>
        <h3>{vi.connectionsPage.visionRoutes}</h3>
        {connections.vision_routes.length === 0 ? (
          <p className="muted">{vi.connectionsPage.noVisionRoutes}</p>
        ) : (
          <ol className="route-list" data-testid="vision-routes">
            {connections.vision_routes.map((route, i) => (
              <li key={`${route.provider}/${route.model}/${i}`}>
                <code>{route.provider}</code> <span className="muted">{route.model}</span>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section>
        <h3>{vi.connectionsPage.search}</h3>
        <ol className="route-list" data-testid="search-backends">
          {connections.search_backends.map((backend, i) => (
            <li key={backend}>
              <code>{backend}</code>
              {i === 0 && <span className="badge ok">1</span>}
            </li>
          ))}
        </ol>
        <p className="muted">
          {connections.firecrawl_base_url
            ? vi.connectionsPage.firecrawlAt(connections.firecrawl_base_url)
            : vi.connectionsPage.firecrawlOff}
        </p>
        <p className="muted">{vi.connectionsPage.searchHint}</p>
      </section>

      <section>
        <h3>{vi.connectionsPage.keys}</h3>
        <ul className="key-list" data-testid="keys">
          {connections.keys.map((key) => (
            <li key={key.name}>
              <code>{key.name}</code>
              <span className={`badge ${key.present ? "ok" : ""}`}>
                {key.present ? vi.connectionsPage.present : vi.connectionsPage.absent}
              </span>
            </li>
          ))}
        </ul>
        <p className="muted">{vi.connectionsPage.keysHint}</p>
      </section>

      <section>
        <h3>{vi.connectionsPage.telegram}</h3>
        {connections.telegram.length === 0 ? (
          <p className="muted">{vi.connectionsPage.noTelegram}</p>
        ) : (
          <ul className="key-list" data-testid="telegram-list">
            {connections.telegram.map((channel) => (
              <li key={channel.agent_id}>
                <code>{channel.agent_id}</code>
                <span className="muted">
                  {vi.connectionsPage.tokenEnv}: <code>{channel.token_env}</code>
                </span>
                <span className={`badge ${channel.configured ? "ok" : ""}`}>
                  {channel.configured
                    ? vi.connectionsPage.configured
                    : vi.connectionsPage.notConfigured}
                </span>
                {channel.ignored && <span className="badge warn">{vi.connectionsPage.ignored}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
