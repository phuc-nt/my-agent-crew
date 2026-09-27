import { useEffect, useRef, useState } from "react";
import { vi } from "../i18n/vi";
import { Icon } from "./ui/icon";

/** Long enough to read the word, short enough that the next copy starts from "Sao chép". */
export const COPIED_MS = 1500;

type State = "idle" | "copied" | "failed";

/**
 * Copies text and says so for a moment.
 *
 * The clipboard API only exists on a secure origin — a phone reaching the server by its
 * LAN address over plain http has none — and a browser may refuse the write even where it
 * exists. So when the write fails the text is shown selected in a box instead: a
 * long-press copy is still one gesture away, where a silent failure would leave the
 * person pasting whatever they had copied before.
 */
export function CopyButton({ text, label, className = "" }: { text: string; label: string; className?: string }) {
  const [state, setState] = useState<State>("idle");
  const timer = useRef<number | undefined>(undefined);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const copy = async () => {
    window.clearTimeout(timer.current);
    try {
      if (!navigator.clipboard?.writeText) throw new Error("clipboard unavailable");
      await navigator.clipboard.writeText(text);
      setState("copied");
      timer.current = window.setTimeout(() => setState("idle"), COPIED_MS);
    } catch {
      setState("failed");
    }
  };

  const copied = state === "copied";
  return (
    <>
      <button
        ref={trigger}
        type="button"
        className={`copy-button ${className}`.trim()}
        data-copied={copied || undefined}
        aria-label={copied ? vi.copy.copied : label}
        title={label}
        onClick={() => void copy()}
      >
        <Icon name={copied ? "check" : "copy"} />
        <span className="copy-label">{copied ? vi.copy.copied : vi.copy.copy}</span>
      </button>
      {/* A changed button name is not announced, so the confirmation is also said here. The
          region stays in the page empty: one that appears with its text is often missed. */}
      <span className="sr-only" aria-live="polite">
        {copied ? vi.copy.copied : ""}
      </span>
      {state === "failed" && (
        <CopyFallback
          text={text}
          onClose={() => {
            setState("idle");
            // The box that had the focus is gone; the button it came from keeps the place.
            trigger.current?.focus();
          }}
        />
      )}
    </>
  );
}

/** The text to copy by hand, already selected so the next gesture is the copy itself. */
function CopyFallback({ text, onClose }: { text: string; onClose: () => void }) {
  const box = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    box.current?.focus();
    box.current?.select();
  }, []);
  return (
    <div
      className="copy-fallback"
      role="status"
      data-testid="copy-fallback"
      onKeyDown={(event) => {
        if (event.key !== "Escape") return;
        event.preventDefault();
        // The drawer and the activity strip listen for Esc too; this one only meant the box.
        event.stopPropagation();
        onClose();
      }}
    >
      <p>{vi.copy.failed}</p>
      <textarea
        ref={box}
        readOnly
        value={text}
        aria-label={vi.copy.manual}
        rows={Math.min(8, text.split("\n").length + 1)}
        onFocus={(event) => event.currentTarget.select()}
      />
      <button type="button" className="link-button" onClick={onClose}>
        {vi.close}
      </button>
    </div>
  );
}

/**
 * Hands the reply to another app through the system share sheet, where the platform has
 * one (iOS Safari does; most desktops do not, so there the button is simply absent).
 * Cancelling the sheet rejects the promise; that is the person's choice, not an error.
 */
function ShareButton({ text }: { text: string }) {
  const share = async () => {
    try {
      await navigator.share({ text });
    } catch {
      // Dismissed, or refused by the platform: the copy button beside this is the fallback.
    }
  };
  return (
    <button type="button" className="copy-button" aria-label={vi.copy.share} title={vi.copy.share} onClick={() => void share()}>
      <Icon name="share" />
      <span className="copy-label">{vi.copy.share}</span>
    </button>
  );
}

/** The actions under an agent reply: copy its markdown as written, and share it where the platform can. */
export function BubbleActions({ text }: { text: string }) {
  const canShare = typeof navigator !== "undefined" && typeof navigator.share === "function";
  return (
    <div className="bubble-actions" data-testid="bubble-actions">
      <CopyButton text={text} label={vi.copy.reply} />
      {canShare && <ShareButton text={text} />}
    </div>
  );
}
