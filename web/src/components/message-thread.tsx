import { agentFileUrl } from "../api/client";
import type { RunInfo } from "../api/types";
import { useAutoScroll } from "../hooks/use-auto-scroll";
import { vi } from "../i18n/vi";
import type { ThreadItem } from "../state/thread-reducer";
import { MarkdownBody } from "./markdown-body";
import { RunProgressHeader } from "./run-progress-header";
import { ToolCallCard } from "./tool-call-card";

interface Props {
  items: ThreadItem[];
  streaming: string | null;
  busy: boolean;
  /** The run this conversation is waiting on, so the wait can say what it is waiting for. */
  liveRun?: RunInfo | null;
  onSuggestion: (text: string) => void;
  echoOnly: boolean;
  agentId: string;
  /** Turns an agent id into its display name for the delegation cards. */
  agentName?: (id: string) => string;
  /** Opens the conversation a delegation created. */
  onOpenConversation?: (conversationId: string) => void;
  /** The master introduces itself by name and names the team it can hand work to. */
  masterName?: string;
  crewNames?: string[];
}

const MEDIA_PREFIX = "MEDIA:";
const FILE_PREFIX = "FILE:";

export function MessageThread({
  items,
  streaming,
  busy,
  liveRun = null,
  onSuggestion,
  echoOnly,
  agentId,
  agentName,
  onOpenConversation,
  masterName,
  crewNames = [],
}: Props) {
  const scroll = useAutoScroll<HTMLElement>();

  if (items.length === 0 && !streaming) {
    const suggestions = [
      ...vi.welcomeSuggestions,
      ...(crewNames.length > 0 ? [vi.welcomeDelegateSuggestion(crewNames[0])] : []),
    ];
    return (
      <section className="thread empty-state" aria-label={vi.agent}>
        <h2>{vi.welcomeTitleFor(masterName ?? vi.agent)}</h2>
        <p>{vi.welcomeBody}</p>
        <p className="muted" data-testid="welcome-crew">
          {crewNames.length > 0 ? vi.welcomeCrew(crewNames) : vi.welcomeNoCrew}
        </p>
        <div className="suggestions">
          {suggestions.map((s) => (
            <button key={s} type="button" className="chip" onClick={() => onSuggestion(s)}>
              {s}
            </button>
          ))}
        </div>
        {echoOnly && <p className="muted">{vi.echoHint}</p>}
      </section>
    );
  }

  return (
    <div className="thread-frame">
      <section className="thread" aria-live="polite" ref={scroll.ref} onScroll={scroll.onScroll}>
      {items.map((item) => (
        <Item
            key={item.id}
            item={item}
            agentId={agentId}
            agentName={agentName}
            onOpenConversation={onOpenConversation}
          />
      ))}
      {streaming !== null && (
        <div className="bubble assistant streaming" data-testid="streaming">
          <span className="bubble-role">{vi.agent}</span>
          <MarkdownBody text={streaming} />
        </div>
      )}
      {/* While the turn is blocked, the thread says what it is blocked on. The
          rail has this already; repeating it here means you do not have to open
          a second panel to learn whether anything is still happening. Without a
          run to read — the very first moment of a turn — it falls back to the
          plain word, which is all that is true yet. */}
      {busy && streaming === null && (
        <div className="thinking" data-testid="thinking">
          {liveRun ? <RunProgressHeader run={liveRun} /> : vi.thinking}
        </div>
      )}
      </section>
      {/* Only worth offering once the tail is actually out of view: shown while the
          thread is already at the bottom it would be a button that does nothing. */}
      {!scroll.atBottom && (
        <button
          type="button"
          className="jump-newest"
          data-testid="jump-newest"
          onClick={scroll.scrollToBottom}
        >
          {vi.jumpToNewest}
        </button>
      )}
    </div>
  );
}

export type ReplyBlock = { kind: "text" | "media" | "file"; value: string };

/**
 * Splits a reply into text blocks, `MEDIA:<path>` lines, which become inline images, and
 * `FILE:<path>` lines, which become download links.
 *
 * Both prefixes are handled here rather than only on the Telegram side, because the same
 * reply text is what the web shows. Leaving `FILE:` unparsed would print the raw line in
 * the chat, so the person on the web would read a path where the person on Telegram got
 * the file itself.
 */
export function splitMedia(text: string): ReplyBlock[] {
  const blocks: ReplyBlock[] = [];
  const pending: string[] = [];
  const flush = () => {
    if (pending.length > 0) blocks.push({ kind: "text", value: pending.join("\n") });
    pending.length = 0;
  };
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    // A bare prefix with nothing after it is not a path, so it stays prose rather than
    // becoming a link to the workspace root.
    if (trimmed.startsWith(MEDIA_PREFIX) && trimmed.length > MEDIA_PREFIX.length) {
      flush();
      blocks.push({ kind: "media", value: trimmed.slice(MEDIA_PREFIX.length).trim() });
    } else if (trimmed.startsWith(FILE_PREFIX) && trimmed.length > FILE_PREFIX.length) {
      flush();
      blocks.push({ kind: "file", value: trimmed.slice(FILE_PREFIX.length).trim() });
    } else {
      pending.push(line);
    }
  }
  flush();
  return blocks;
}

/** The last segment of a workspace path, which is what the link should read as. */
function fileName(path: string): string {
  const parts = path.split("/").filter((part) => part !== "");
  return parts[parts.length - 1] ?? path;
}

function Item({
  item,
  agentId,
  agentName,
  onOpenConversation,
}: {
  item: ThreadItem;
  agentId: string;
  agentName?: (id: string) => string;
  onOpenConversation?: (conversationId: string) => void;
}) {
  if (item.kind === "tool")
    return (
      <ToolCallCard item={item} agentName={agentName} onOpenConversation={onOpenConversation} />
    );
  // Not a bubble: a note is an aside about the work, not a turn in the conversation.
  // Giving it a bubble would make the agent look like it had said two things.
  if (item.kind === "note")
    return (
      <div className="thread-note" data-testid="message-note">
        {item.text}
      </div>
    );
  const role = item.kind === "user" ? vi.you : vi.agent;
  const assistant = item.kind === "assistant";
  const blocks = assistant ? splitMedia(item.text) : [{ kind: "text" as const, value: item.text }];
  return (
    <div className={`bubble ${item.kind}`} data-testid={`message-${item.kind}`}>
      <span className="bubble-role">
        {role}
        {assistant && item.model && <span className="muted"> · {item.model}</span>}
      </span>
      {blocks.map((block, i) =>
        block.kind === "media" ? (
          <img
            key={i}
            className="media"
            src={agentFileUrl(agentId, block.value)}
            alt={vi.mediaAlt(block.value)}
            loading="lazy"
          />
        ) : block.kind === "file" ? (
          // `download` rather than a plain link: these are the formats a browser would
          // otherwise try to open in place, and a CSV rendered as a wall of text in a new
          // tab is not what "send me the file" meant.
          <a
            key={i}
            className="attachment"
            data-testid="message-file"
            href={agentFileUrl(agentId, block.value)}
            download={fileName(block.value)}
          >
            {vi.attachmentDownload(fileName(block.value))}
          </a>
        ) : assistant ? (
          <MarkdownBody key={i} text={block.value} />
        ) : (
          <p key={i}>{block.value}</p>
        ),
      )}
    </div>
  );
}
