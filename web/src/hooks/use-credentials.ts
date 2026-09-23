// The keys and hosts the crew connects with, as the connections page edits them. Values
// only ever go out: the server answers with which names are set, never with a secret.
// Every change is applied to the running crew by the server, so the registry is
// refreshed after it to show the providers and search backends that change brought.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { CredentialCheck, CredentialsInfo } from "../api/types";

export interface CredentialsController {
  info: CredentialsInfo | null;
  /** The list could not be loaded. A row's own failure is thrown to that row instead. */
  error: string | null;
  save: (name: string, value: string) => Promise<CredentialsInfo>;
  remove: (name: string) => Promise<CredentialsInfo>;
  check: (name: string) => Promise<CredentialCheck>;
}

export function useCredentials(onChanged?: () => void): CredentialsController {
  const [info, setInfo] = useState<CredentialsInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api
      .credentials()
      .then((next) => {
        if (!live) return;
        setInfo(next);
        setError(null);
      })
      .catch((e: unknown) => {
        if (live) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      live = false;
    };
  }, []);

  const applied = useCallback(
    (next: CredentialsInfo) => {
      setInfo(next);
      onChanged?.();
      return next;
    },
    [onChanged],
  );

  const save = useCallback(
    async (name: string, value: string) => applied(await api.setCredential(name, value)),
    [applied],
  );
  const remove = useCallback(
    async (name: string) => applied(await api.removeCredential(name)),
    [applied],
  );
  const check = useCallback((name: string) => api.checkCredential(name), []);

  return { info, error, save, remove, check };
}
