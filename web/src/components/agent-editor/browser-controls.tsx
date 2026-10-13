import { useId, useState } from "react";
import type { BrowserConnection, BrowserMode } from "../../api/types";
import { hostLines } from "../../hooks/browser-hosts";
import type { AgentDraft } from "../../hooks/use-agent-draft";
import { vi } from "../../i18n/vi";
import { Field } from "./fields";

interface Props {
  form: AgentDraft;
  readOnly: boolean;
  /** The machine's browser, from the connections the page already read; absent while that
   * read is on its way and from a server older than the browser. */
  machine?: BrowserConnection;
}

const MODES: BrowserMode[] = ["off", "read", "act"];

const sameList = (a: string[], b: string[]) => a.length === b.length && a.every((line, at) => line === b[at]);

/** Why an agent that asks for a browser gets none on this machine. The switch comes first:
 * with it off, whether a browser is installed changes nothing. */
function machineWarning(machine: BrowserConnection | undefined): string | undefined {
  if (machine?.enabled === false) return vi.browser.machineOffForAgent;
  if (machine?.installed === false) return vi.browser.machineMissingForAgent;
  return undefined;
}

/**
 * The hosts opened without asking, one per line.
 *
 * The text being typed lives here and the draft holds the list it stands for, as the form's
 * other lists do: a blank line is spacing, and a line break just pressed is not yet a host.
 * The box is rewritten only when the draft holds another list than the one its text was last
 * read as, which is a revert, another agent, or a save the server answered differently. The
 * list is remembered beside the text rather than read off it again: a file edited by hand may
 * hold a line this box would write otherwise, and that must not have the two chase each other.
 */
function HostsField({ form, readOnly }: Pick<Props, "form" | "readOnly">) {
  const hintId = useId();
  const errorId = useId();
  const hosts = form.draft.browser_hosts ?? [];
  const [box, setBox] = useState(() => ({ text: hosts.join("\n"), list: hosts }));
  if (!sameList(box.list, hosts)) setBox({ text: hosts.join("\n"), list: hosts });
  const error = form.problems.browserHosts;

  return (
    <Field label={vi.browser.hosts} hint={vi.browser.hostsHint} hintId={hintId} error={error} errorId={errorId}>
      <textarea
        className="mono"
        rows={4}
        aria-label={vi.browser.hosts}
        aria-describedby={error ? `${hintId} ${errorId}` : hintId}
        aria-invalid={error ? true : undefined}
        spellCheck={false}
        autoCapitalize="none"
        value={box.text}
        disabled={readOnly}
        onChange={(e) => {
          const list = hostLines(e.target.value);
          setBox({ text: e.target.value, list });
          form.set("browser_hosts", list);
        }}
      />
    </Field>
  );
}

/**
 * Whether the agent has a browser, and which hosts it opens without asking.
 *
 * Both sit with the tools because they are the say over six of them: the browser's tools
 * are handed outside the allow-list, by this key and by nothing else. Under the select is
 * the line for the option chosen, and under that, when the machine cannot give a browser,
 * the reason the choice brings no tool yet.
 *
 * The host list shows while the agent has a browser. Set back to off, the list stays in the
 * form as it was, so choosing a level again finds it. A line the save is held for keeps the
 * box on screen whatever the level, since a problem with no box to fix it in is a dead end.
 *
 * A server older than the browser sends no such key, and this draws nothing for its agents.
 */
export function BrowserControls({ form, readOnly, machine }: Props) {
  const modeHint = useId();
  const warningId = useId();
  if (form.original?.browser === undefined) return null;
  const t = vi.browser;
  const mode = form.draft.browser ?? "off";
  const warning = mode === "off" ? undefined : machineWarning(machine);

  return (
    <>
      <h3>{t.title}</h3>
      <p className="muted">{t.sectionHint}</p>
      <label className="field">
        <span className="field-label">{t.mode}</span>
        <select
          aria-label={t.mode}
          aria-describedby={warning ? `${modeHint} ${warningId}` : modeHint}
          value={mode}
          disabled={readOnly}
          onChange={(e) => form.set("browser", e.target.value as BrowserMode)}
        >
          {MODES.map((value) => (
            <option key={value} value={value}>
              {t.modeOption[value]}
            </option>
          ))}
        </select>
        <span className="muted field-hint" id={modeHint}>
          {t.modeHint[mode]}
        </span>
        {warning && (
          <span className="field-hint warn-text" id={warningId} data-testid="browser-machine-warning">
            {warning}
          </span>
        )}
      </label>
      {(mode !== "off" || form.problems.browserHosts !== undefined) && <HostsField form={form} readOnly={readOnly} />}
    </>
  );
}

/** Under the tool picker: why the browser's tools have no tick there. Nothing for an agent
 * of a server that knows no browser. */
export function BrowserToolsNote({ form }: Pick<Props, "form">) {
  if (form.original?.browser === undefined) return null;
  return <p className="muted field-hint">{vi.browser.outsideList}</p>;
}
