import { agentFileUrl } from "../api/client";
import { vi } from "../i18n/vi";
import { Icon } from "./ui/icon";

/**
 * The line the Telegram channel writes into a person's message for each file it saved to
 * the agent's inbox (`TELEGRAM_ATTACHMENT_LINE` in my_agent_crew/texts_telegram.py). It is
 * a wire format the server produces, not copy this UI shows, so it is matched here beside
 * its parser; only a whole line in exactly that shape counts, so a person typing the
 * words in a sentence keeps their sentence.
 */
const ATTACHMENT_LINE = /^\[Tệp đính kèm đã lưu: (.+)\]$/;
/** What a browser shows inline everywhere; HEIC and the rest download instead. */
const IMAGE = /\.(jpe?g|png|gif|webp)$/i;
/** The saved name leads with the moment it arrived, which says nothing the thread does not. */
const SAVED_AT = /^\d{8}-\d{6}-/;

export type AttachmentBlock = { kind: "text" | "attachment"; value: string };

/** The last segment of a workspace path, which is what a link to it should read as. */
export function fileName(path: string): string {
  const parts = path.split("/").filter((part) => part !== "");
  return parts[parts.length - 1] ?? path;
}

/** Splits a person's message into what they wrote and the files the channel saved for them. */
export function splitAttachments(text: string): AttachmentBlock[] {
  const blocks: AttachmentBlock[] = [];
  const pending: string[] = [];
  const flush = () => {
    if (pending.length > 0) blocks.push({ kind: "text", value: pending.join("\n") });
    pending.length = 0;
  };
  for (const line of text.split("\n")) {
    const match = ATTACHMENT_LINE.exec(line.trim());
    if (match) {
      flush();
      blocks.push({ kind: "attachment", value: match[1].trim() });
    } else {
      pending.push(line);
    }
  }
  flush();
  return blocks;
}

/**
 * A file the person sent, as something to open: a photo as a thumbnail that opens full
 * size, anything else as a named download chip. The path is the one the channel saved to
 * inside the agent's workspace, so the agent's own files route serves it.
 */
export function AttachmentChip({ agentId, path }: { agentId: string; path: string }) {
  const href = agentFileUrl(agentId, path);
  const name = fileName(path).replace(SAVED_AT, "");
  if (IMAGE.test(path)) {
    return (
      <a
        className="attachment-thumb"
        data-testid="attachment-image"
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={vi.attachmentOpen(name)}
      >
        <img src={href} alt={vi.attachmentImage(name)} loading="lazy" />
      </a>
    );
  }
  return (
    <a className="attachment" data-testid="attachment-file" href={href} download={name}>
      <Icon name="download" />
      {vi.attachmentDownload(name)}
    </a>
  );
}
