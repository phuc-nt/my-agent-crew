import { useCallback, useEffect, useState } from "react";
import { vi } from "../i18n/vi";
import { disablePush, enablePush, PushRefused, pushState, testPush, type PushState } from "../lib/push";

/** This device's notifications as the inbox shows them, and the presses that change them. */
export function usePush() {
  const [state, setState] = useState<PushState | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const reread = useCallback(() => pushState().then(setState, () => setState("unsupported")), []);
  useEffect(() => void reread(), [reread]);

  const act = useCallback(
    async (press: () => Promise<string | null>, failed: string) => {
      setBusy(true);
      setNote(null);
      try {
        setNote(await press());
      } catch (error) {
        setNote(error instanceof PushRefused ? vi.push.refused : failed);
      } finally {
        setBusy(false);
        await reread();
      }
    },
    [reread],
  );

  const enable = () => act(async () => (await enablePush(), null), vi.push.failed);
  const disable = () => act(async () => (await disablePush(), null), vi.push.failed);
  const test = () =>
    act(async () => {
      const status = await testPush();
      return status >= 200 && status < 300 ? vi.push.testSent : vi.push.testFailed(status);
    }, vi.push.testFailed(0));

  return { state, busy, note, enable, disable, test };
}

export type Push = ReturnType<typeof usePush>;
