/**
 * What the page on show said went wrong: how many reports it made, as far as the panel heard it
 * out, the newest few as text, and a button that sends them to the agent. The page wrote every
 * word of them, so they are drawn as text and nothing else, and they reach the agent only when the
 * person presses the button, in a message that says what they are (`lib/error-report.ts`).
 *
 * Sending saves the canvas first, like the question about a passage, so the agent reads what the
 * person sees. The errors sent are the ones listed when the button is pressed. Once they are sent
 * the button stays off until the page reports something new.
 */

import { useState } from "react";
import type { MessageCanvas } from "../../api/artifact-types";
import type { PageReport } from "../../hooks/use-page-report";
import { vi } from "../../i18n/vi";
import { errorReport } from "../../lib/error-report";
import { FRAME_REPORTS_MAX, type FrameError, where } from "../../lib/frame-messages";
import { showHiddenChars } from "../../lib/hidden-chars";
import type { SendResult } from "../../lib/send-result";
import type { AskDisabled } from "./canvas-ask";

type Props = {
  artifactId: string;
  title: string;
  report: PageReport;
  /** Why asking is off for now, if it is; sending is off for the same reasons. */
  disabled: AskDisabled;
  /** The panel's last save, which no version may be missing from: the version, or null. */
  flush(): Promise<number | null>;
  /** The chat's send; where it is absent the errors are listed and there is no way to send them. */
  onAsk?(canvas: MessageCanvas, question: string): Promise<SendResult>;
};

/** What was sent: how many errors of how many the page had reported by then. */
type Sent = { reported: number; errors: number };

export function CanvasErrors({ artifactId, title, report, disabled, flush, onAsk }: Props) {
  const [open, setOpen] = useState(false);
  const [sending, setSending] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [sent, setSent] = useState<Sent | null>(null);
  const spent = sent !== null && sent.reported === report.count;

  /** The words of the failure, or null once the server has the message. */
  async function post(ask: NonNullable<Props["onAsk"]>, errors: FrameError[], version: number): Promise<string | null> {
    if ((await flush()) === null) return vi.canvas.pageErrors.notSaved;
    const result = await ask({ artifact_id: artifactId, selection: null }, errorReport(title, version, errors));
    return result.status === "failed" ? result.error : null;
  }

  const send = async () => {
    if (!onAsk) return;
    const { recent, count, version } = report;
    setSending(true);
    setFailure(null);
    let failed: string | null;
    try {
      failed = await post(onAsk, recent, version);
    } catch {
      failed = vi.sendFailed.other;
    }
    setSending(false);
    if (failed === null) setSent({ reported: count, errors: recent.length });
    else setFailure(failed);
  };

  if (report.count === 0) return null;
  const { pageErrors } = vi.canvas;
  // The frame stops hearing a page there, so that many may be fewer than the page reported.
  const more = report.count >= FRAME_REPORTS_MAX;
  return (
    <div className="canvas-errors" role="group" aria-label={pageErrors.group}>
      <div className="canvas-errors-bar">
        <span className="canvas-errors-count">{pageErrors.count(report.count, more)}</span>
        <button type="button" className="ghost" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? pageErrors.hide : pageErrors.show}
        </button>
        {onAsk && (
          <button type="button" className="primary" disabled={sending || spent || disabled !== null} onClick={() => void send()}>
            {pageErrors.send}
          </button>
        )}
      </div>
      {onAsk && disabled && <p className="canvas-ask-note">{vi.canvas.ask[disabled]}</p>}
      {failure && (
        <div className="notice error" role="alert">
          {failure}
        </div>
      )}
      {spent && (
        <p className="canvas-ask-note" role="status">
          {pageErrors.sent(sent.errors)}
        </p>
      )}
      {open && (
        <ol className="canvas-errors-list">
          {report.recent.map((error, at) => (
            <li key={at}>
              <span className="canvas-error-message">{showHiddenChars(error.message)}</span>
              {where(error) !== "" && <span className="canvas-error-place">{showHiddenChars(where(error))}</span>}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
