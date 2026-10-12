import { useEffect, useRef, useState } from "react";

/** The raise a notice offers, and where the keyboard goes once it is through. */
export function useFocusAfterRaise(onRaiseCap: (cost_cap_usd: number) => Promise<void>) {
  // A raise from a notice often takes the notice, or its button, away with the control
  // the keyboard was on. Once the screen has caught up, the keyboard goes where the person
  // carries on: the composer when the raise let it write, or the raise still on offer.
  const mainRef = useRef<HTMLElement>(null);
  const [afterRaise, setAfterRaise] = useState(0);
  const raiseFromNotice = async (cost_cap_usd: number) => {
    await onRaiseCap(cost_cap_usd);
    setAfterRaise((n) => n + 1);
  };
  useEffect(() => {
    if (afterRaise === 0) return;
    mainRef.current
      ?.querySelector<HTMLElement>(".composer textarea:not(:disabled), [data-testid=over-budget] > .link-button")
      ?.focus();
  }, [afterRaise]);
  return { mainRef, raiseFromNotice };
}
