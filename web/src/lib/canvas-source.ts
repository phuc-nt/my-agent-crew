/**
 * Where a canvas says it came from, as the server writes it
 * (`my_agent_crew/tools/artifact_source_ref.py`): `workspace:<agent id>/<path>` for a file in an
 * agent's workspace, or a plain link to the page it was taken from. Anything else is no source: a
 * canvas made here has none, and what is stored is read again here rather than trusted.
 */

export type CanvasSource =
  | { kind: "workspace"; agentId: string; path: string }
  /** `href` is the address as the browser reads it; `host` is where it leads. */
  | { kind: "url"; href: string; host: string };

/** Cut at the first slash: an agent id holds none, a path may hold any. */
const WORKSPACE = /^workspace:([^/]+)\/(.+)$/;
const WEB = ["http:", "https:"];

export function parseSource(source: string): CanvasSource | null {
  const file = WORKSPACE.exec(source);
  if (file) return { kind: "workspace", agentId: file[1], path: file[2] };
  let url: URL;
  try {
    url = new URL(source);
  } catch {
    return null;
  }
  return WEB.includes(url.protocol) ? { kind: "url", href: url.href, host: url.host } : null;
}
