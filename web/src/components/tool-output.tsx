import { useState } from "react";
import { vi } from "../i18n/vi";
import { FAILED_KEPT_CHARS } from "../lib/step-preview";

interface Props {
  text: string;
  /** The call did not go through: it failed, or it was refused. */
  failed: boolean;
}

/**
 * What a tool handed back, on a run's step and on the chat card alike.
 *
 * Folded until asked for when the call went through: the row above already says it did, and
 * what came back is detail. A call that failed is the other way round. What came back is the
 * reason, and a refusal ends with what to do instead, so it is open without a press and, at
 * the length a step keeps of a failure, read whole: wrapped over as many lines as it takes,
 * with no box to scroll inside.
 *
 * The chat card holds everything a tool handed back, which for a command that failed may be
 * pages. Past the length a step keeps, it is still open and all there, in the box that scrolls.
 */
export function ToolOutput({ text, failed }: Props) {
  // Null until the person presses. A step heard live is on the row before it ends, so
  // "open because it failed" cannot be settled once when the row is first drawn.
  const [asked, setAsked] = useState<boolean | null>(null);
  const open = asked ?? failed;
  const whole = failed && Array.from(text).length <= FAILED_KEPT_CHARS;
  return (
    <>
      <button type="button" className="link-button" onClick={() => setAsked(!open)}>
        {open ? vi.hideOutput : vi.showOutput}
      </button>
      {open && <pre className={whole ? "tool-output whole" : "tool-output"}>{text}</pre>}
    </>
  );
}
