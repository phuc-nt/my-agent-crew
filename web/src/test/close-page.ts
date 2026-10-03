/**
 * The page is about to close. The event carries `returnValue` as a plain field, so a test can read
 * what a listener set on it.
 */
export function closePage(): Event & { returnValue: unknown } {
  const event = new Event("beforeunload", { cancelable: true });
  Object.defineProperty(event, "returnValue", { value: undefined, writable: true });
  window.dispatchEvent(event);
  return event as Event & { returnValue: unknown };
}

/** The page is about to close; true when something asked the person to stay first. */
export const askedToStay = (): boolean => closePage().defaultPrevented;
