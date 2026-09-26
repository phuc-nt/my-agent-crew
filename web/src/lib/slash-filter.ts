import type { CommandInfo } from "../api/types";
import { fold } from "../components/conversation-search";

/**
 * The word being typed as a command: the whole box while it is "/" and then a name with
 * no space yet, or `null`. A "/" further in ("đi /home") or a command already given its
 * arguments is text, not a request for the list.
 */
export function slashQuery(text: string): string | null {
  return /^\/\S*$/.test(text) ? text.slice(1) : null;
}

/**
 * The commands worth showing for what was typed after the "/": names that start with it
 * first, then names that merely contain it, each tier in the agent's own order. Accents
 * are optional, the way the conversation search treats them (đ included).
 */
export function filterCommands(commands: CommandInfo[], query: string): CommandInfo[] {
  const needle = fold(query.trim());
  if (needle === "") return commands;
  const prefix: CommandInfo[] = [];
  const inside: CommandInfo[] = [];
  for (const command of commands) {
    const name = fold(command.name);
    if (name.startsWith(needle)) prefix.push(command);
    else if (name.includes(needle)) inside.push(command);
  }
  return [...prefix, ...inside];
}

/**
 * The box once `name` is picked, in the shape the server expands: "/name", a space, then
 * the arguments. The "/name" being typed is replaced, and so is a command already given
 * its arguments ("/review src/x.py" becomes "/fix src/x.py"); any other text, a path
 * that merely starts with "/" included, is kept whole as the arguments.
 */
export function insertCommand(text: string, name: string, commands: CommandInfo[]): string {
  const lead = /^\/(\S*)\s*/.exec(text);
  const replaces = lead !== null && (slashQuery(text) !== null || commands.some((c) => c.name === lead[1]));
  const rest = (replaces && lead ? text.slice(lead[0].length) : text).trim();
  return rest ? `/${name} ${rest}` : `/${name} `;
}
