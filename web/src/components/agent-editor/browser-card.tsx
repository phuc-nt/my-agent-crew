import { useId } from "react";
import type { AgentBrowser, BrowserMode, BrowserTab } from "../../api/types";
import { type AgentBrowserController, useAgentBrowser } from "../../hooks/use-agent-browser";
import { vi } from "../../i18n/vi";
import { BrowserLogin } from "./browser-login";
import { BrowserSignedIn } from "./browser-signed-in";

interface Props {
  agentId: string;
  /** The agent's `browser` key as its file has it; absent from a server older than the key. */
  savedMode?: BrowserMode;
  /** Its `browser_hosts` as its file has them: an agent with a list is shown every host of it. */
  savedHosts?: string[];
  /** Opens the conversation a tab belongs to, on a page that has a way to. */
  onOpenConversation?: (conversationId: string) => void;
}

/** Where the browser stands, in one line. What runs is said first: a browser left up by a
 * setting since changed is still there to be stopped. A window a person signs in through
 * holds the profile, so the agent has no browser to start while it is open. */
function stateLine(browser: AgentBrowser): string {
  const t = vi.browser.card;
  if (browser.running) return t.running(browser.tabs.length);
  if (browser.login?.open) return t.loginOpen;
  if (!browser.enabled) return t.machineOff;
  if (!browser.installed) return t.notInstalled;
  return t.stopped;
}

interface TabProps {
  tab: BrowserTab;
  control: AgentBrowserController;
  onOpenConversation?: (conversationId: string) => void;
}

/** One tab: the name the agent gave it, what it shows, whose it is, and whether a call is on it. */
function TabRow({ tab, control, onOpenConversation }: TabProps) {
  const t = vi.browser.card;
  const conversation = tab.conversation_id;
  return (
    <li className="browser-tab" data-testid={`browser-tab-${tab.id}`}>
      <div className="browser-tab-head">
        <code>{tab.label}</code>
        <span className="browser-tab-title">{tab.title || t.untitled}</span>
      </div>
      <div className="browser-tab-meta muted">
        <span className="browser-tab-host">{tab.host || t.blank}</span>
        {conversation === null ? (
          <span>{t.scheduled}</span>
        ) : onOpenConversation ? (
          <button
            type="button"
            className="link-button"
            aria-label={t.conversationOf(tab.label)}
            onClick={() => onOpenConversation(conversation)}
          >
            {t.conversation}
          </button>
        ) : (
          <span>{t.inConversation}</span>
        )}
        <span>{tab.busy ? t.inUse : t.idle(tab.idle_seconds)}</span>
      </div>
      <div className="credential-actions">
        <button
          type="button"
          aria-label={t.closeTabNamed(tab.label)}
          disabled={control.pending !== null}
          onClick={() => control.closeTab(tab.id)}
        >
          {control.pending === tab.id ? t.closing : t.closeTab}
        </button>
      </div>
    </li>
  );
}

/**
 * What the agent's browser is doing now: stopped or running, and each tab it has open.
 *
 * It stands outside the form because nothing here is saved: stopping the browser and closing
 * a tab happen at once, to what is running, and the profile stays as it is. Neither asks
 * first. Nothing is lost that the agent cannot open again, and what it is signed in to stays.
 * While one of them is in flight every button waits, and the state is read again after it.
 *
 * Under what runs are the window a person signs in through and the hosts the browser may
 * still be signed in to, each where the server tells of it: one older than them tells of
 * neither, and the card is as it was.
 *
 * An agent with no browser and none running has no card, and neither has one on a server
 * older than the route. A state that never arrived is said only for an agent whose file
 * asks for a browser, where the card was to be expected.
 */
export function BrowserCard({ agentId, savedMode, savedHosts, onOpenConversation }: Props) {
  const stopNote = useId();
  const control = useAgentBrowser(agentId, savedMode);
  const { browser, note, pending } = control;
  const t = vi.browser.card;
  const quiet = browser ? browser.mode === "off" && !browser.running : note === null || (savedMode ?? "off") === "off";
  if (quiet) return null;

  return (
    <section className="editor-section browser-card" data-testid="browser-card">
      <h3>{vi.browser.title}</h3>
      {browser && (
        <p className="browser-state">
          {/* The idle time moves at every read, so it stays out of the region that is read
              aloud when it changes. */}
          <span role="status" data-testid="browser-state">
            {stateLine(browser)}
          </span>
          {browser.running && (
            <span className="muted" data-testid="browser-activity">
              {browser.busy ? t.working : t.idle(browser.idle_seconds ?? 0)}
            </span>
          )}
        </p>
      )}
      {browser && browser.tabs.length > 0 && (
        <ul className="browser-tabs" aria-label={t.tabs}>
          {browser.tabs.map((tab) => (
            <TabRow key={tab.id} tab={tab} control={control} onOpenConversation={onOpenConversation} />
          ))}
        </ul>
      )}
      {browser?.running && (
        <div className="credential-actions">
          <button type="button" className="danger" aria-describedby={stopNote} disabled={pending !== null} onClick={control.stop}>
            {pending === "stop" ? t.stopping : t.stop}
          </button>
          <span className="muted field-hint" id={stopNote}>
            {t.stopNote}
          </span>
        </div>
      )}
      {browser?.login && <BrowserLogin login={browser.login} control={control} />}
      {browser && browser.logins !== undefined && (
        <BrowserSignedIn logins={browser.logins} ownHosts={savedHosts} more={browser.logins_more} />
      )}
      {note && (
        <p className={`credential-note ${note.tone}`} role="status" data-testid="browser-note">
          {note.text}
        </p>
      )}
    </section>
  );
}
