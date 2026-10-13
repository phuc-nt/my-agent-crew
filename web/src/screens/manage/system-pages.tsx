import { LivePreviewSetting } from "../../components/canvas/live-preview-setting";
import { ConnectionsPanel } from "../../components/connections-panel";
import { SettingsPanel } from "../../components/settings-panel";
import { StatsPanel } from "../../components/stats-panel";
import type { CredentialsController } from "../../hooks/use-credentials";
import type { McpController } from "../../hooks/use-mcp-servers";
import type { RegistryController } from "../../hooks/use-registry";
import { vi } from "../../i18n/vi";
import type { ManageProps } from "./manage-props";

interface SystemParts {
  registry: RegistryController;
  credentials: CredentialsController;
  mcp: McpController;
  rebuilt: () => Promise<void>;
}

/** The pages for the bill, the connections and the settings, as the screen draws them. */
export function systemPages(props: ManageProps, { registry, credentials, mcp, rebuilt }: SystemParts) {
  return (
    <>
      {props.section === "costs" && (
        <StatsPanel stats={props.stats} agentName={props.agentName} />
      )}
      {props.section === "connections" &&
        (registry.connections ? (
          <ConnectionsPanel
            connections={registry.connections}
            credentials={credentials}
            mcp={mcp}
            agentName={props.agentName}
            onChanged={rebuilt}
          />
        ) : (
          <p className="muted">{registry.error ?? vi.manage.loading}</p>
        ))}
      {props.section === "settings" && (
        <>
          {/* The one thing here the person sets, and for this device alone, comes before the
              machine's configuration, which is read on this page and changed elsewhere. */}
          <LivePreviewSetting />
          <SettingsPanel
            settings={props.settings}
            agents={props.agents}
            onNavigate={props.onNavigate}
            versions={props.versions}
          />
        </>
      )}
    </>
  );
}
