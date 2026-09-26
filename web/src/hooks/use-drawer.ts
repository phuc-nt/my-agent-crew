import { useCallback, useEffect, useRef, useState } from "react";

/**
 * A panel that slides over the page on a small screen: whether it is open, and the focus
 * handoff a covering surface owes the keyboard — into the panel when it opens, back to the
 * control that opened it when it closes, so nobody is left focused on something hidden.
 *
 * `enabled` is false wherever the panel is a column of the layout instead; there it is
 * simply always there, and "open" means nothing.
 */
export function useDrawer(enabled: boolean) {
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);
  // Opened for a purpose (⌘K opens it for the search box), the drawer hands focus to that
  // control instead of to its first one.
  const focusOnOpen = useRef<HTMLElement | null>(null);

  // Widening past the phone layout turns the drawer back into a column; it must not
  // reappear as an overlay if the window narrows again later.
  useEffect(() => {
    if (!enabled) setOpen(false);
  }, [enabled]);

  useEffect(() => {
    if (open) (focusOnOpen.current ?? panelRef.current?.querySelector<HTMLElement>("button, input"))?.focus();
    else if (wasOpen.current) triggerRef.current?.focus();
    focusOnOpen.current = null;
    wasOpen.current = open;
  }, [open]);

  return {
    open: enabled && open,
    show: useCallback((focus?: HTMLElement | null) => {
      focusOnOpen.current = focus ?? null;
      setOpen(true);
    }, []),
    hide: useCallback(() => setOpen(false), []),
    panelRef,
    triggerRef,
  };
}
