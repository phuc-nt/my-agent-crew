import { useEffect, useId, useRef, useState } from "react";
import type { BrowserSignedIn as SignedIn } from "../../api/types";
import { vi } from "../../i18n/vi";
import { calendarDate } from "../../lib/relative-time";

/** How many hosts an agent with no list of its own is shown before it is asked for the rest. */
const FIRST = 8;

interface Props {
  /** Null where there is nothing to tell: no browser, or none ever closed on the profile. */
  logins: SignedIn[] | null;
  /** The agent's `browser_hosts` as its file has them. */
  ownHosts?: string[];
}

/**
 * Where the agent's browser may still be signed in: each host with the day the last cookie
 * that counts for it runs out.
 *
 * An agent with hosts of its own is told of each of them, also of one that holds nothing,
 * and all of them are shown: the list is the person's own, and as long as they made it. An
 * agent with none is told of whatever its browser holds, which can be many: the first few
 * are shown, and a button brings the rest. Once pressed the button is gone and the keyboard
 * is put on the list it filled, since a button that vanishes under it leaves it nowhere.
 *
 * Nothing here is said aloud when it changes: it changes at a read, not at something the
 * person did.
 */
export function BrowserSignedIn({ logins, ownHosts }: Props) {
  const labelId = useId();
  const list = useRef<HTMLUListElement>(null);
  const [all, setAll] = useState(false);
  const t = vi.browser.signedIn;

  useEffect(() => {
    if (all) list.current?.focus();
  }, [all]);

  if (logins === null) return null;
  if (logins.length === 0) {
    return (
      <p className="browser-signed-in muted" data-testid="browser-signed-in-none">
        {t.none}
      </p>
    );
  }
  const whole = all || (ownHosts ?? []).length > 0;
  const shown = whole ? logins : logins.slice(0, FIRST);
  const rest = logins.length - shown.length;

  return (
    <div className="browser-signed-in" data-testid="browser-signed-in">
      <p className="field-label" id={labelId}>
        {t.label}
      </p>
      <ul className="browser-hosts" aria-labelledby={labelId} ref={list} tabIndex={-1}>
        {shown.map(({ host, until }, at) => (
          <li key={`${at}:${host}`} className={until === null ? "browser-host muted" : "browser-host"}>
            <span className="browser-host-name">{host}</span>
            {" · "}
            {until === null ? t.nothing : t.until(calendarDate(until))}
          </li>
        ))}
      </ul>
      {rest > 0 && (
        <button type="button" className="chip" onClick={() => setAll(true)}>
          {t.more(rest)}
        </button>
      )}
      <p className="muted field-hint">{t.caveat}</p>
    </div>
  );
}
