import { useId, useState } from "react";
import type { ComputerMode } from "../../api/types";
import type { AgentDraft } from "../../hooks/use-agent-draft";
import { vi } from "../../i18n/vi";
import { Field } from "./fields";

interface Props {
  form: AgentDraft;
  readOnly: boolean;
}

const MODES: ComputerMode[] = ["off", "on"];

/** The server's refusal of each key (`agents/profile_desktop.py`), after the agent's id. */
const REFUSED = { computer: /: computer must be /, computer_apps: /: computer_apps must be / };

const sameList = (a: string[], b: string[]) => a.length === b.length && a.every((line, at) => line === b[at]);

/** The list a box of text stands for: one application per line, as the server keeps them:
 * trimmed, blank lines dropped, each once. */
export function appLines(text: string): string[] {
  return [...new Set(text.split("\n").map((line) => line.trim()).filter((line) => line !== ""))];
}

/** What the last save was refused for, when it was this key: shown beside its control. */
function refusedFor(form: AgentDraft, key: keyof typeof REFUSED): string | undefined {
  return form.error && REFUSED[key].test(form.error) ? form.error : undefined;
}

/**
 * The applications the agent may read and act in, one per line.
 *
 * As with the browser's hosts, the text being typed lives here and the draft holds the list
 * it stands for; the box is rewritten only when the draft holds another list than the one
 * its text was last read as. A refused save leaves both alone, so what was typed stays.
 */
function AppsField({ form, readOnly }: Props) {
  const hintId = useId();
  const errorId = useId();
  const apps = form.draft.computer_apps ?? [];
  const [box, setBox] = useState(() => ({ text: apps.join("\n"), list: apps }));
  if (!sameList(box.list, apps)) setBox({ text: apps.join("\n"), list: apps });
  const error = refusedFor(form, "computer_apps");
  const t = vi.desktop.editor;

  return (
    <Field label={t.apps} hint={t.appsHint} hintId={hintId} error={error} errorId={errorId}>
      <textarea
        rows={4}
        aria-label={t.apps}
        aria-describedby={error ? `${hintId} ${errorId}` : hintId}
        aria-invalid={error ? true : undefined}
        spellCheck={false}
        autoCapitalize="none"
        value={box.text}
        disabled={readOnly}
        data-testid="desktop-apps"
        onChange={(e) => {
          const list = appLines(e.target.value);
          setBox({ text: e.target.value, list });
          form.set("computer_apps", list);
        }}
      />
    </Field>
  );
}

/**
 * Whether the agent may use the machine's screen and keyboard, and in which applications.
 *
 * Both sit with the tools because they are the say over four of them: the desktop's tools
 * come with `computer: on` and with nothing else. The mode is sent as the word itself, never
 * as a switch. The helper on the machine and its permissions are the machine owner's, and a
 * line says so; an empty list of applications is an agent that only looks.
 *
 * The list shows while the agent is on, and while a save is refused for it. A server older
 * than the desktop sends no such key, and this draws nothing for its agents.
 */
export function DesktopControls({ form, readOnly }: Props) {
  const modeHint = useId();
  const errorId = useId();
  if (form.original?.computer === undefined) return null;
  const t = vi.desktop.editor;
  const mode = form.draft.computer ?? "off";
  const error = refusedFor(form, "computer");
  const appsRefused = refusedFor(form, "computer_apps") !== undefined;

  return (
    <div data-testid="desktop-controls">
      <h3>{vi.desktop.title}</h3>
      <p className="muted">{t.sectionHint}</p>
      <label className="field">
        <span className="field-label">{t.mode}</span>
        <select
          aria-label={t.mode}
          aria-describedby={error ? `${modeHint} ${errorId}` : modeHint}
          aria-invalid={error ? true : undefined}
          value={mode}
          disabled={readOnly}
          onChange={(e) => form.set("computer", e.target.value as ComputerMode)}
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
        {error && (
          <span className="field-error" id={errorId} data-testid="desktop-mode-error">
            {error}
          </span>
        )}
      </label>
      {(mode === "on" || appsRefused) && <AppsField form={form} readOnly={readOnly} />}
      <p className="muted field-hint" data-testid="desktop-helper-note">
        {t.helperNote}
      </p>
    </div>
  );
}

/** Under the tool picker: why the desktop's tools have no tick there. Nothing for an agent
 * of a server that knows no desktop. */
export function DesktopToolsNote({ form }: Pick<Props, "form">) {
  if (form.original?.computer === undefined) return null;
  return <p className="muted field-hint">{vi.desktop.outsideList}</p>;
}
