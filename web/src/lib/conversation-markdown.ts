import remarkGfm from "remark-gfm";
import remarkParse from "remark-parse";
import { unified } from "unified";
import type { ConversationDetail } from "../api/types";
import { vi } from "../i18n/vi";
import { pad2 } from "./relative-time";

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
  return `UTC${sign}${hours}${minutes ? `:${pad2(minutes)}` : ""}`;
}

/** "26/09/2026 14:05 (UTC+7)", built by hand: Intl's vi-VN dates differ between ICU builds. */
export function exportStamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const day = `${pad2(date.getDate())}/${pad2(date.getMonth() + 1)}/${date.getFullYear()}`;
  return `${day} ${pad2(date.getHours())}:${pad2(date.getMinutes())} (${zoneLabel(date)})`;
}

/** The slice of a parsed markdown tree the export reads: what each block is and where. */
interface Block {
  type: string;
  depth?: number;
  position?: { start: { offset?: number }; end: { offset?: number } };
  children?: Block[];
}

// Read the way the thread reads a reply, so a heading or a code block inside a list item or a
// quote is found where it sits, not only at the start of a line.
const markdown = unified().use(remarkParse).use(remarkGfm);
const FENCE_OPEN = /^(`{3,}|~{3,})/;
const FENCE_CLOSE = /^ {0,3}(`{3,}|~{3,})[ \t]*$/;
const UNDERLINE = /[=-]+[ \t]*$/;
// The raw HTML blocks that end only on a closer, never on an empty line: how each opens, what
// ends it (any of the four tags ends a "<pre"), and the closer to write when the reply never did.
const RAW_HTML: {
  open: RegExp;
  closed: RegExp;
  put: (opened: RegExpExecArray) => string;
}[] = [
  {
    open: /^<(pre|script|style|textarea)(?=[\s>]|$)/i,
    closed: /<\/(pre|script|style|textarea)>/i,
    put: (m) => `</${m[1].toLowerCase()}>`,
  },
  { open: /^<!--/, closed: /-->/, put: () => "-->" },
  { open: /^<\?/, closed: /\?>/, put: () => "?>" },
  { open: /^<!\[CDATA\[/, closed: /\]\]>/, put: () => "]]>" },
  { open: /^<![a-z]/i, closed: />/, put: () => ">" },
];

/**
 * A message body that stays inside its turn.
 *
 * Only a turn heading may say who spoke: a reply's own headings are its sections, so they
 * move two levels down, below the turns, in a quote or a list as much as at the top, and an
 * underline that would make the lines above it a heading is set apart from them. Code is left
 * as written. A code or raw HTML block the reply never closed — one cut off at the token
 * limit — is closed, or it would swallow every turn after it; one inside a list or a quote ends
 * where that does.
 */
function nested(body: string): string {
  const text = body.replace(/\r\n?/g, "\n");
  const tree: Block = markdown.parse(text);
  // Each edit cuts `cut` characters at `at` and puts `put` there; made from the last one back,
  // so the places of those before it still hold.
  const edits: { at: number; cut: number; put: string }[] = [];
  const visit = (node: Block) => {
    for (const child of node.children ?? []) {
      const start = child.position?.start.offset;
      const end = child.position?.end.offset;
      if (child.type === "heading" && child.depth && start !== undefined && end !== undefined) {
        const lastLine = text.lastIndexOf("\n", end - 1) + 1;
        if (lastLine <= start) {
          // "## Tóm tắt" is one line, and the heading starts at its marks.
          edits.push({ at: start, cut: child.depth, put: "#".repeat(Math.min(6, child.depth + 2)) });
        } else {
          // "Tóm tắt\n---": an empty line now parts them, ">" in a quote so the quote goes on.
          const underline = text.slice(lastLine, end);
          const quoteMarks = underline.slice(0, underline.search(UNDERLINE)).trimEnd();
          edits.push({ at: lastLine, cut: 0, put: `${quoteMarks}\n` });
        }
      }
      visit(child);
    }
  };
  visit(tree);
  // Only a block at the top of the body runs on past its end into the turns after it.
  const last = tree.children?.at(-1);
  const from = last?.position?.start.offset;
  if (last?.type === "html" && from !== undefined) {
    const block = text.slice(from, last.position?.end.offset).trimStart();
    for (const { open, closed, put } of RAW_HTML) {
      const opened = open.exec(block);
      if (!opened) continue;
      if (!closed.test(block.slice(opened[0].length))) {
        edits.push({ at: text.length, cut: 0, put: `\n${put(opened)}` });
      }
      break;
    }
  }
  if (last?.type === "code" && from !== undefined) {
    const lines = text.slice(from, last.position?.end.offset).split("\n");
    const marks = FENCE_OPEN.exec(lines[0])?.[1];
    const close = lines.length > 1 ? FENCE_CLOSE.exec(lines[lines.length - 1])?.[1] : undefined;
    // Closed only by a run of the same mark, at least as long as the one that opened it.
    if (marks && !(close?.[0] === marks[0] && close.length >= marks.length)) {
      edits.push({ at: text.length, cut: 0, put: `\n${marks}` });
    }
  }
  let out = text;
  for (const { at, cut, put } of edits.sort((a, b) => b.at - a.at)) {
    out = out.slice(0, at) + put + out.slice(at + cut);
  }
  return out;
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
