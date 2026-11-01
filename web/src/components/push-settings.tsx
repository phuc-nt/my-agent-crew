import type { Push } from "../hooks/use-push";
import { vi } from "../i18n/vi";

const SAYS = {
  install: vi.push.install,
  denied: vi.push.denied,
  unsupported: vi.push.unsupported,
} as const;

/**
 * Notifications on this device, where the person reads what they would be told of: a press
 * to turn them on, or, once on, a test push and a way back. What stands in the way (an
 * iPhone outside the Home Screen, a blocked permission) is said in place of the press.
 */
export function PushSettings({ push }: { push: Push }) {
  const { state, busy, note } = push;
  if (state === null) return null;
  return (
    <section className={`push-settings ${state}`} aria-label={vi.push.title}>
      <h3>{vi.push.title}</h3>
      {state === "off" && (
        <>
          <p className="muted">{vi.push.offHint}</p>
          <button type="button" className="primary" disabled={busy} onClick={push.enable}>
            {vi.push.enable}
          </button>
        </>
      )}
      {state === "on" && (
        <>
          <p className="muted">{vi.push.onHint}</p>
          <div className="push-actions">
            <button type="button" disabled={busy} onClick={push.test}>
              {vi.push.test}
            </button>
            <button type="button" disabled={busy} onClick={push.disable}>
              {vi.push.disable}
            </button>
          </div>
        </>
      )}
      {state in SAYS && <p className="muted">{SAYS[state as keyof typeof SAYS]}</p>}
      {note && (
        <p className="push-note" role="status">
          {note}
        </p>
      )}
    </section>
  );
}
