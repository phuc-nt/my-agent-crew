import { vi } from "../i18n/vi";

const AGENT = "agent:";

/**
 * Who wrote a canvas version, as the panel names them: the person is "bạn", an agent its
 * name. The server writes "user" or "agent:<id>", so an agent whose id is "user" still
 * reads as that agent. `agentName` already falls back to the id of an agent that is gone.
 */
export function authorLabel(author: string, agentName: (id: string) => string): string {
  if (author === "user") return vi.canvas.you;
  if (author.startsWith(AGENT)) return agentName(author.slice(AGENT.length));
  return author;
}
