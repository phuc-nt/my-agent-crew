import { useCallback, useRef, useState } from "react";
import type { RestoreRequest } from "../../components/composer";

/** The words on their way back to the composer, and the way to send some there. */
export function useRestoreText() {
  // Text handed back to the composer from outside: a queueing POST that itself failed, or
  // words Stop pulled off the server's queue. `restoreNonce` is a plain counter rather than
  // `Date.now()` so two restores in the same millisecond (Stop, then a failed send right
  // after) still read as two distinct requests to the composer's own nonce check.
  const [restore, setRestore] = useState<RestoreRequest | null>(null);
  const restoreNonce = useRef(0);
  const restoreText = useCallback((text: string) => {
    restoreNonce.current += 1;
    setRestore({ nonce: restoreNonce.current, text });
  }, []);
  return { restore, restoreText };
}
