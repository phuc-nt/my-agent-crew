import { useId, useState } from "react";
import { vi } from "../i18n/vi";
import { isLongPrinted, printedLines } from "../lib/script-handoff";

/**
 * What a script job's script printed, under the message that handed it to the agent.
 *
 * Under the bubble and not in it, as the note a message carried from a canvas is: the
 * bubble's colour is the person's own words, here the schedule's prompt, and this is
 * whatever the script's tools handed it. It is shown as the text it is, in the type of a
 * terminal, wrapped, in a box that scrolls on its own past a height.
 *
 * Open while it reads at a glance. A long one stays folded behind its label, which says how
 * long it is, so that a morning's report does not bury the thread it opens.
 */
export function ScriptPrinted({ text }: { text: string }) {
  const [open, setOpen] = useState(() => !isLongPrinted(text));
  const bodyId = useId();
  return (
    <div className="script-printed" data-testid="script-printed" role="group" aria-label={vi.scriptHandoff.printed}>
      <button
        type="button"
        className="chip script-printed-toggle"
        aria-expanded={open}
        aria-controls={open ? bodyId : undefined}
        onClick={() => setOpen((was) => !was)}
      >
        {vi.scriptHandoff.toggle(printedLines(text))}
      </button>
      {open && (
        // In the tab order, so a text taller than its box can be scrolled without a mouse.
        <pre className="script-printed-text" id={bodyId} data-testid="script-printed-text" tabIndex={0}>
          {text}
        </pre>
      )}
      <p className="script-printed-note">{vi.scriptHandoff.asData}</p>
    </div>
  );
}
