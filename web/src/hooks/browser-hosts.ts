// The hosts an agent's browser may open without asking, as the form holds them.

/** The server's own rule for one entry (`HOST_PATTERN` in my_agent_crew/agents/profile_browser.py):
 * a host name, or `*.` and a host name for every host under it. No scheme, port or path. */
const HOST = /^(\*\.)?([a-z0-9-]+\.)*[a-z0-9-]+$/;

/** The list a box of text stands for: one host per line, written small, blank lines dropped.
 * The server takes lower case only, and a name typed with a capital means the same host. */
export function hostLines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim().toLowerCase())
    .filter((line) => line !== "");
}

/** The first entry the server would refuse, or undefined when it would take them all. */
export function badHost(hosts: string[]): string | undefined {
  return hosts.find((host) => !HOST.test(host));
}
