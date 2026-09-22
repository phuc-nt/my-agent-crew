// The crew's registry: every tool, and everything the crew talks to on the outside.
// Both are read-only and change only when an agent is edited or the server restarts, so
// they load once and refresh on demand rather than polling.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { ConnectionsInfo, RegistryTool } from "../api/types";

export interface RegistryController {
  tools: RegistryTool[];
  connections: ConnectionsInfo | null;
  /** True until the first answer arrives, so a page can tell "empty" from "not yet". */
  loading: boolean;
  /** What went wrong, if the load failed. An empty registry and a broken one look the
   * same on screen otherwise, and here they mean very different things. */
  error: string | null;
  refresh: () => Promise<void>;
}

export function useRegistry(): RegistryController {
  const [tools, setTools] = useState<RegistryTool[]>([]);
  const [connections, setConnections] = useState<ConnectionsInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [nextTools, nextConnections] = await Promise.all([api.listTools(), api.connections()]);
      setTools(nextTools);
      setConnections(nextConnections);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { tools, connections, loading, error, refresh };
}
