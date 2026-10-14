import { useState } from "react";
import { api } from "../api/client";
import type { DesktopConnection, DesktopPermissions } from "../api/types";
import { vi } from "../i18n/vi";
import { errorText } from "../lib/error-text";
import { MetricCard } from "./ui/metric-card";

type Permission = keyof DesktopPermissions;
const PERMISSIONS: readonly Permission[] = ["screen_recording", "accessibility"];

interface Props {
  desktop: DesktopConnection;
  /** Reads the page again; the card's own row is redrawn from what it answers. */
  onChanged: () => Promise<void> | void;
}

/** One permission as the helper told it: granted, missing, or not said. */
function PermissionRow({ name, value }: { name: Permission; value: boolean | null }) {
  const t = vi.desktop.machine;
  const [tone, word] = value === true ? ["ok", t.granted] : value === false ? ["warn", t.missing] : ["", t.unknown];
  return (
    <li data-testid={`desktop-permission-${name}`}>
      <span>{vi.desktop.permission[name]}</span>
      <span className={`badge ${tone}`.trim()}>{word}</span>
    </li>
  );
}

/**
 * The machine's desktop helper: whether one answered, which version, whether the screen is
 * locked or asleep, and the two macOS permissions it holds.
 *
 * The helper and its permissions are the machine owner's. The one thing the card sends is a
 * request for macOS to ask for them, and only on a press: it may put a dialog on the owner's
 * screen, so nothing sends it on load, on a timer or again by itself. macOS asks once per
 * permission; one still missing after a press is the owner's to grant in System Settings, and
 * the card says so.
 */
export function ConnectionsDesktopCard({ desktop, onChanged }: Props) {
  const t = vi.desktop.machine;
  const [asking, setAsking] = useState(false);
  const [asked, setAsked] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ask = async () => {
    setAsking(true);
    setError(null);
    try {
      await api.askDesktopPermissions();
      setAsked(true);
    } catch (e) {
      setError(errorText(e));
    }
    // Whatever the answer, the helper may have changed since the page was read.
    try {
      await onChanged();
    } finally {
      setAsking(false);
    }
  };

  if (!desktop.present) {
    return (
      <MetricCard title={vi.desktop.title} testId="desktop-machine">
        <p className="muted" data-testid="desktop-machine-state">
          {t.absent}
        </p>
      </MetricCard>
    );
  }
  const askable = PERMISSIONS.some((name) => desktop[name] !== true);
  const stillMissing = PERMISSIONS.filter((name) => desktop[name] === false).map((name) => vi.desktop.permission[name]);
  return (
    <MetricCard title={vi.desktop.title} testId="desktop-machine">
      <div className="row wrap" data-testid="desktop-machine-state">
        <span className="badge ok">{t.present}</span>
        {desktop.version && <span className="muted">{t.version(desktop.version)}</span>}
        {desktop.locked && <span className="badge warn">{t.locked}</span>}
        {desktop.display_asleep && <span className="badge warn">{t.asleep}</span>}
      </div>
      <h4 className="connections-subtitle">{t.permissionsLabel}</h4>
      <ul className="key-list" data-testid="desktop-permissions">
        {PERMISSIONS.map((name) => (
          <PermissionRow key={name} name={name} value={desktop[name]} />
        ))}
      </ul>
      {askable && (
        <div className="desktop-ask">
          <button type="button" onClick={() => void ask()} disabled={asking} data-testid="desktop-ask">
            {asking ? t.asking : t.ask}
          </button>
          <p className="muted">{t.askHint}</p>
        </div>
      )}
      {asked && stillMissing.length > 0 && (
        <p className="credential-note warn" data-testid="desktop-still-missing">
          {t.stillMissing(stillMissing.join(", "))}
        </p>
      )}
      {error && (
        <p className="credential-note danger" role="alert" data-testid="desktop-ask-error">
          {error}
        </p>
      )}
    </MetricCard>
  );
}
