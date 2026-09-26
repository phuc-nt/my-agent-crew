import { agentFileUrl } from "../api/client";
import type { RunInfo } from "../api/types";
import { useAutoScroll } from "../hooks/use-auto-scroll";
import { vi } from "../i18n/vi";
import type { ThreadItem } from "../state/thread-reducer";
import { MarkdownBody } from "./markdown-body";
import { RunProgressHeader } from "./run-progress-header";
import { ToolCallCard } from "./tool-call-card";
import { AgentAvatar } from "./ui/agent-avatar";
import { BrandMark } from "./ui/brand-mark";
import { Icon } from "./ui/icon";

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
  const speaker = agentName?.(agentId) ?? vi.agent;

  if (items.length === 0 && !streaming) {
    const suggestions = [
      ...vi.welcomeSuggestions,
      ...(crewNames.length > 0 ? [vi.welcomeDelegateSuggestion(crewNames[0])] : []),
    ];
    return (
      <section className="thread empty-state" aria-label={vi.agent}>
        <div className="welcome">
          <BrandMark size={56} />
          <h2>{vi.welcomeTitleFor(masterName ?? vi.agent)}</h2>
          <p className="welcome-body">{vi.welcomeBody}</p>
          <p className="muted" data-testid="welcome-crew">
            {crewNames.length > 0 ? vi.welcomeCrew(crewNames) : vi.welcomeNoCrew}
          </p>
          <div className="suggestions">
            {suggestions.map((s) => (
              <button key={s} type="button" className="suggestion" onClick={() => onSuggestion(s)}>
                <span>{s}</span>
                <Icon name="arrow-up" className="suggestion-go" />
              </button>
            ))}
          </div>
          {echoOnly && <p className="muted echo-hint">{vi.echoHint}</p>}
        </div>
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
            speaker={speaker}
            agentName={agentName}
            onOpenConversation={onOpenConversation}
          />
      ))}
      {streaming !== null && (
        <div className="bubble assistant streaming" data-testid="streaming">
          <Speaker id={agentId} name={speaker} />
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
          <AgentAvatar id={agentId} name={speaker} size="sm" />
          {liveRun ? <RunProgressHeader run={liveRun} /> : <span className="thinking-text">{vi.thinking}</span>}
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
          <Icon name="arrow-down" />
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

/** Who said the reply: the agent's tile and name, and the model that wrote it when known. */
function Speaker({ id, name, model }: { id: string; name: string; model?: string | null }) {
  return (
    <span className="bubble-role">
      <AgentAvatar id={id} name={name} size="sm" />
      <span className="speaker-name">{name}</span>
      {model && <span className="muted speaker-model"> · {model}</span>}
    </span>
  );
}

/** The last segment of a workspace path, which is what the link should read as. */
function fileName(path: string): string {
  const parts = path.split("/").filter((part) => part !== "");
  return parts[parts.length - 1] ?? path;
}

function Item({
  item,
  agentId,
  speaker,
  agentName,
  onOpenConversation,
}: {
  item: ThreadItem;
  agentId: string;
  speaker: string;
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
  const assistant = item.kind === "assistant";
  const blocks = assistant ? splitMedia(item.text) : [{ kind: "text" as const, value: item.text }];
  return (
    <div className={`bubble ${item.kind}`} data-testid={`message-${item.kind}`}>
      {/* Your own messages need no name on screen — the side they sit on says it — but a
          screen reader reading the thread in order still needs to hear who spoke. */}
      {assistant ? (
        <Speaker id={agentId} name={speaker} model={item.model} />
      ) : (
        <span className="sr-only">{vi.you}</span>
      )}
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
            <Icon name="download" />
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
