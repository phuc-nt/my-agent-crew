import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Tone } from "./metric-card";

interface Props {
  /** What the pill says while closed: the one figure worth seeing without opening it. */
  label: ReactNode;
  /** Names the card that opens, for assistive tech. */
  popoverLabel: string;
  /** Tints the pill's border and dot; absent is the neutral grey. */
  tone?: Tone;
  /** A status dot before the label, for pills that report a state. */
  dot?: boolean;
  title?: string;
  testId?: string;
  className?: string;
  children: ReactNode;
}

/**
 * A pill in a header that opens a card of detail under it.
 *
 * The pill carries the headline, the card the breakdown and the switches, so a header
 * holds three short pills instead of every control in a row. The card closes on Escape,
 * on a click outside and on a second click of the pill; clicks inside it (a switch
 * being flipped) leave it open so several settings can be changed in one visit.
 */
export function PopoverChip({ label, popoverLabel, tone, dot = false, title, testId, className = "", children }: Props) {
  const [open, setOpen] = useState(false);
  const anchor = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (anchor.current && !anchor.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="popover-anchor" ref={anchor}>
      <button
        type="button"
        className={`pill${tone ? ` ${tone}` : ""}${open ? " open" : ""} ${className}`.trim()}
        aria-expanded={open}
        aria-haspopup="dialog"
        title={title}
        data-testid={testId}
        onClick={() => setOpen((value) => !value)}
      >
        {dot && <span className="pill-dot" aria-hidden="true" />}
        {label}
        <span className="pill-caret" aria-hidden="true">
          ⌄
        </span>
      </button>
      {open && (
        <div className="popover" role="dialog" aria-label={popoverLabel}>
          {children}
        </div>
      )}
    </div>
  );
}
