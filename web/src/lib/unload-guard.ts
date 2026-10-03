/**
 * Makes the browser ask before the page closes. Held while some text exists only in this page:
 * unsaved, with no draft kept for it on the device.
 */

/** Starts asking; the returned function stops it. Each call holds its own listener, so one holder
 *  letting go leaves the others in place. */
export function guardUnload(): () => void {
  const ask = (event: BeforeUnloadEvent) => {
    event.preventDefault();
    // Older engines show the prompt only for a set return value.
    event.returnValue = "";
  };
  window.addEventListener("beforeunload", ask);
  return () => window.removeEventListener("beforeunload", ask);
}
