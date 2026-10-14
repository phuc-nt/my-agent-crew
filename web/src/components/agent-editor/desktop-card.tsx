import { useId } from "react";
import { agentFileUrl } from "../../api/client";
import type { ComputerMode, DesktopConnection } from "../../api/types";
import { useAgentDesktop } from "../../hooks/use-agent-desktop";
import { vi } from "../../i18n/vi";

interface Props {
  agentId: string;
  /** The agent's `computer` key as its file has it; absent from a server older than the key. */
  savedMode?: ComputerMode;
  /** Its `computer_apps` as its file has them. A change is read again at once. */
  savedApps?: string[];
}

const PERMISSIONS = ["screen_recording", "accessibility"] as const;

/** What stands between the agent and the screen, one line each, or the one line saying that
 *  nothing does. With no helper there is nothing else to tell. */
export function machineLines(machine: DesktopConnection): string[] {
  const t = vi.desktop.card;
  if (!machine.present) return [t.noHelper];
  const lines: string[] = [];
  if (machine.locked) lines.push(t.locked);
  if (machine.display_asleep) lines.push(t.asleep);
  for (const name of PERMISSIONS) {
    if (machine[name] === false) lines.push(t.missing(vi.desktop.permission[name]));
    else if (machine[name] === null) lines.push(t.unknown(vi.desktop.permission[name]));
  }
  return lines.length > 0 ? lines : [t.ready];
}

/**
 * The agent's desktop as it stands now: its mode and applications, the machine as it is for
 * it, and a picture a person may try.
 *
 * It stands outside the form because nothing here is saved. The try takes one picture the way
 * the agent's own tool does, held to the same applications, into the agent's workspace; the
 * server's sentence for why there is none is shown as it is. It is offered only to an agent
 * that is on, and waits while it runs.
 *
 * A server older than the desktop draws no card, and neither does an agent the route does not
 * know.
 */
export function DesktopCard({ agentId, savedMode, savedApps }: Props) {
  const hintId = useId();
  const control = useAgentDesktop(agentId, savedMode, savedApps);
  const { desktop, readError, shooting, shot, refused } = control;
  const t = vi.desktop.card;
  if (savedMode === undefined || control.missing) return null;

  return (
    <section className="editor-section desktop-card" data-testid="desktop-card">
      <h3>{vi.desktop.title}</h3>
      {desktop && (
        <>
          <p data-testid="desktop-mode">{t.mode[desktop.mode]}</p>
          {desktop.mode === "on" && (
            <p className="muted" data-testid="desktop-apps-line">
              {desktop.apps.length > 0 ? t.apps(desktop.apps.join(", ")) : t.lookOnly}
            </p>
          )}
          <ul className="desktop-machine-lines" role="status" data-testid="desktop-machine-lines">
            {machineLines(desktop.machine).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </>
      )}
      {desktop?.mode === "on" && (
        <div className="credential-actions">
          <button type="button" aria-describedby={hintId} disabled={shooting} onClick={control.tryShot} data-testid="desktop-try">
            {shooting ? t.shooting : t.tryShot}
          </button>
          <span className="muted field-hint" id={hintId}>
            {t.tryHint}
          </span>
        </div>
      )}
      {shot && (
        <a
          className="desktop-shot"
          href={agentFileUrl(agentId, shot.path)}
          target="_blank"
          rel="noreferrer"
          data-testid="desktop-shot"
        >
          <img src={agentFileUrl(agentId, shot.path)} alt={t.shotAlt(shot.width, shot.height)} />
        </a>
      )}
      {refused && (
        <p className="credential-note warn" role="status" data-testid="desktop-refused">
          {refused}
        </p>
      )}
      {readError && (
        <p className="credential-note danger" role="status" data-testid="desktop-read-error">
          {t.readFailed(readError)}
        </p>
      )}
    </section>
  );
}
