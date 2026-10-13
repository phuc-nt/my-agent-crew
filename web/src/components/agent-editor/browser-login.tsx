import { useId, useState } from "react";
import type { BrowserLogin as Login } from "../../api/types";
import type { AgentBrowserController } from "../../hooks/use-agent-browser";
import { vi } from "../../i18n/vi";
import { clockTime } from "../../lib/relative-time";

interface Props {
  login: Login;
  control: AgentBrowserController;
}

/** What is in the way of a window, in a sentence. An agent with no browser gets none: the
 * card says why already. A word this page does not know reads as "not now". */
function whyNot(why: string): string | null {
  if (why === "off") return null;
  const known: Record<string, string> = vi.browser.login.why;
  return Object.hasOwn(known, why) ? known[why] : vi.browser.login.notNow;
}

/**
 * The window a person signs in through on the agent's own profile: the way to open one, the
 * one that is open, or what is in the way.
 *
 * The window is shown on the screen of the machine the crew runs on, and nothing of it
 * reaches this page but the moment it closes by itself. Opening one is refused in the
 * server's own sentence, which the card shows as its note; what was typed stays for
 * another try, and is cleared only once a window opened on it.
 *
 * The line of an open window is said aloud once, when it opens: its closing time does not
 * move. What is in the way is plain text, since a call of the agent comes and goes at every
 * read.
 */
export function BrowserLogin({ login, control }: Props) {
  const hintId = useId();
  const [address, setAddress] = useState("");
  const t = vi.browser.login;
  const waiting = control.pending !== null;

  if (login.open) {
    return (
      <div className="browser-login">
        <p role="status" data-testid="browser-login-open">
          {t.open(login.until === null ? null : clockTime(login.until))}
        </p>
        <div className="credential-actions">
          <button type="button" disabled={waiting} onClick={control.closeLogin}>
            {control.pending === "done" ? t.closing : t.done}
          </button>
        </div>
      </div>
    );
  }

  if (!login.available) {
    const why = whyNot(login.why);
    if (why === null) return null;
    return (
      <p className="browser-login muted" data-testid="browser-login-why">
        {why}
      </p>
    );
  }

  const open = async () => {
    if (await control.openLogin(address.trim())) setAddress("");
  };

  return (
    <div className="browser-login">
      <label className="field">
        <span className="field-label">{t.address}</span>
        <input
          type="text"
          inputMode="url"
          className="mono"
          aria-label={t.address}
          spellCheck={false}
          autoCapitalize="none"
          autoComplete="off"
          value={address}
          onChange={(e) => setAddress(e.target.value)}
        />
      </label>
      <div className="credential-actions">
        <button type="button" aria-describedby={hintId} disabled={waiting} onClick={() => void open()}>
          {control.pending === "login" ? t.starting : t.start}
        </button>
        <span className="muted field-hint" id={hintId}>
          {t.hint}
        </span>
      </div>
    </div>
  );
}
