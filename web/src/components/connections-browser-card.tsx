import type { BrowserConnection } from "../api/types";
import { useBrowsersRunning } from "../hooks/use-browsers-running";
import { vi } from "../i18n/vi";
import { MetricCard } from "./ui/metric-card";

interface Props {
  browser: BrowserConnection;
  /** The name an agent goes by. Without it, an agent is named by its id. */
  agentName?: (id: string) => string;
}

/** What keeps a browser from starting, and the command that installs it. The machine's own
 * Chrome has no command: its owner installs it, or goes back to the crew's Chromium. */
function Missing({ browser }: { browser: BrowserConnection }) {
  const t = vi.browser.machine;
  if (!browser.missing) return null;
  const chrome = browser.missing === "browser" && !browser.install_command;
  return (
    <p className="warn-text" data-testid="browser-missing">
      {chrome ? t.missingChrome : browser.missing === "playwright" ? t.missingPlaywright : t.missingChromium}
      {browser.install_command && (
        <>
          {" "}
          {t.installWith} <code>{browser.install_command}</code>
        </>
      )}
    </p>
  );
}

/**
 * The machine's browser: whether the crew may start one, which one, what is missing, and
 * whose is up now.
 *
 * Nothing here sets anything. The switch is a key of the machine's own file, read when the
 * server starts, and each agent's use of the browser is set on that agent's page. Whose is up
 * changes with nobody on this page doing anything, so the card keeps that one line current.
 */
export function ConnectionsBrowserCard({ browser, agentName }: Props) {
  const t = vi.browser.machine;
  const names = useBrowsersRunning(browser).map((id) => agentName?.(id) ?? id);
  return (
    <MetricCard title={vi.browser.title} testId="browser-machine">
      {browser.enabled ? (
        <div className="row wrap" data-testid="browser-machine-state">
          <span className="badge ok">{t.on}</span>
          <span>{t.channel[browser.channel] ?? browser.channel}</span>
          {browser.version && <span className="muted">{browser.version}</span>}
        </div>
      ) : (
        <p className="muted" data-testid="browser-machine-state">
          {t.off}
        </p>
      )}
      <Missing browser={browser} />
      <p className="muted" data-testid="browser-machine-running">
        {names.length > 0 ? t.running(names.length, names.join(", ")) : t.noneRunning}
      </p>
    </MetricCard>
  );
}
