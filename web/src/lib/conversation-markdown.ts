import type { ConversationDetail } from "../api/types";
import { vi } from "../i18n/vi";

const pad = (n: number) => String(n).padStart(2, "0");

/**
 * "UTC+7", "UTC+5:30", "UTC-3": the zone the export's clock readings are in.
 *
 * The server stores UTC, but a timestamp nobody can place on their own day is not worth
 * exporting, so the file carries local times — and names the zone, because the file
 * outlives the machine it was saved on.
 */
function zoneLabel(date: Date): string {
  const offset = -date.getTimezoneOffset();
  const sign = offset < 0 ? "-" : "+";
  const hours = Math.floor(Math.abs(offset) / 60);
  const minutes = Math.abs(offset) % 60;
  return `UTC${sign}${hours}${minutes ? `:${pad(minutes)}` : ""}`;
}

/** "26/09/2026 14:05 (UTC+7)", built by hand: Intl's vi-VN dates differ between ICU builds. */
export function exportStamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const day = `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()}`;
  return `${day} ${pad(date.getHours())}:${pad(date.getMinutes())} (${zoneLabel(date)})`;
}

// CommonMark's line shapes: up to three spaces of indent, then the marks. A backtick
// fence's info string holds no backtick, or the line is inline code, not a fence.
const FENCE_OPEN = /^( {0,3})(`{3,}(?=[^`]*$)|~{3,})/;
const FENCE_CLOSE = /^ {0,3}(`{3,}|~{3,})[ \t]*$/;
const HEADING = /^( {0,3})(#{1,6})(?=[ \t]|$)/;
const UNDERLINE = /^ {0,3}(?:=+|-+)[ \t]*$/;

/**
 * A message body that stays inside its turn.
 *
 * Only a turn heading may say who spoke: a reply's own headings are its sections, so they
 * move two levels down, below the turns, and an underline that would make the line above it
 * a heading is set apart from it. Code is left as written. A block the reply never closed —
 * one cut off at the token limit — is closed, or it would swallow every turn after it.
 */
function nested(body: string): string {
  const lines: string[] = [];
  let fence: { indent: string; marks: string } | null = null;
  for (const line of body.split(/\r\n|\r|\n/)) {
    if (fence) {
      const close = FENCE_CLOSE.exec(line)?.[1];
      if (close && close[0] === fence.marks[0] && close.length >= fence.marks.length) fence = null;
      lines.push(line);
      continue;
    }
    const open = FENCE_OPEN.exec(line);
    if (open) fence = { indent: open[1], marks: open[2] };
    else if (UNDERLINE.test(line) && lines.length > 0 && lines[lines.length - 1].trim() !== "") lines.push("");
    lines.push(line.replace(HEADING, (_, indent: string, marks: string) => indent + "#".repeat(Math.min(6, marks.length + 2))));
  }
  // Indented as it opened, so a block inside a list item closes there, not after the list.
  if (fence) lines.push(fence.indent + fence.marks);
  return lines.join("\n");
}

/**
 * The conversation as a markdown document: its title, then each turn under a heading that
 * says who spoke and when.
 *
 * Only what was said is kept. Tool results and an assistant message that only called a
 * tool are the agent's working, which the reader of an exported chat never saw in the
 * thread either; they would bury the replies under JSON.
 */
export function conversationMarkdown(detail: ConversationDetail, agentName: string): string {
  const parts = [`# ${detail.title.trim() || vi.newConversation}`];
  for (const message of detail.messages) {
    if (message.role !== "user" && message.role !== "assistant") continue;
    const body = message.content.trim();
    if (body === "") continue;
    const who = message.role === "user" ? vi.you : agentName;
    parts.push(`## ${who} · ${exportStamp(message.created_at)}`, nested(body));
  }
  return `${parts.join("\n\n")}\n`;
}

/** A file name from the title: characters a file system refuses become dashes. */
export function markdownFileName(title: string): string {
  const safe = title
    .replace(/[\\/:*?"<>|\u0000-\u001f]+/g, "-")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^[.-]+|[.-]+$/g, "");
  return `${safe || vi.newConversation}.md`;
}

/** Saves text as a file through a temporary link, the one download path every browser shares. */
export function downloadText(name: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  // Revoked on the next task: Safari starts the download after click() returns.
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
