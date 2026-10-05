import { agentFileUrl } from "../api/client";
import type { RunInfo } from "../api/types";
import { useAutoScroll } from "../hooks/use-auto-scroll";
import { vi } from "../i18n/vi";
import type { WritingItem } from "../lib/canvas-writing";
import { type ReplyBlock, splitMedia } from "../lib/reply-blocks";
import type { ThreadItem } from "../state/thread-reducer";
import { AttachmentChip, fileName, splitAttachments, type AttachmentBlock } from "./attachment-chip";
import type { CanvasLinks } from "./canvas/canvas-card";
import { CanvasNoteChip } from "./canvas/canvas-note-chip";
import { CanvasRefChip } from "./canvas/canvas-ref-chip";
import { CanvasWritingCard } from "./canvas/canvas-writing-card";
import { BubbleActions } from "./copy-button";
import { ForkButton } from "./fork-button";
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
  /** Draws a write to a canvas as the canvas, with a way to open it; absent keeps the plain tool card. */
  canvas?: CanvasLinks;
  /** The canvases the agent is writing right now, a card each, and the way to watch one fill in;
   *  absent where the screen does not follow the writing. */
  writing?: { items: WritingItem[]; onShow(key: number): void };
  /** The master introduces itself by name and names the team it can hand work to. */
  masterName?: string;
  crewNames?: string[];
  /** Rewinds and forks the conversation at a saved user message; absent hides the button
   *  entirely, and it is also hidden while `busy` — see `use-fork.ts` for why: the
   *  `local-N` resolution it does counts bubbles by position, which a turn still writing
   *  new ones would throw off mid-click. */
  onFork?: (item: ThreadItem) => void;
}

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
  canvas,
  writing,
  masterName,
  crewNames = [],
  onFork,
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
      <section
        className="thread"
        aria-live="polite"
        ref={scroll.ref}
        onScroll={scroll.onScroll}
        data-following={scroll.atBottom || undefined}
      >
      {items.map((item) => (
        <Item
            key={item.id}
            item={item}
            agentId={agentId}
            speaker={speaker}
            agentName={agentName}
            onOpenConversation={onOpenConversation}
            canvas={canvas}
            onFork={!busy ? onFork : undefined}
          />
      ))}
      {streaming !== null && (
        <div className="bubble assistant streaming" data-testid="streaming">
          <Speaker id={agentId} name={speaker} />
          <MarkdownBody text={streaming} />
        </div>
      )}
      {writing?.items.map((item) => (
        <CanvasWritingCard key={item.key} item={item} onShow={writing.onShow} />
      ))}
      {/* While the turn is blocked, the thread says what it is blocked on. The
          rail has this already; repeating it here means you do not have to open
          a second panel to learn whether anything is still happening. Without a
          run to read — the very first moment of a turn — it falls back to the
          plain word, which is all that is true yet. A canvas being written says
          what is happening by its card, so the wait has nothing to add. */}
      {busy && streaming === null && !writing?.items.length && (
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

function Item({
  item,
  agentId,
  speaker,
  agentName,
  onOpenConversation,
  canvas,
  onFork,
}: {
  item: ThreadItem;
  agentId: string;
  speaker: string;
  agentName?: (id: string) => string;
  onOpenConversation?: (conversationId: string) => void;
  canvas?: CanvasLinks;
  /** Already `undefined` while busy — `MessageThread` clears it before passing it down —
   *  so `Item` only has to decide whether the item itself can ever be forked. */
  onFork?: (item: ThreadItem) => void;
}) {
  if (item.kind === "tool")
    return (
      <ToolCallCard item={item} agentName={agentName} onOpenConversation={onOpenConversation} canvas={canvas} />
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
  // What a person sent through Telegram arrives as lines naming the saved files; those
  // become the photo or the file again rather than a path in their own bubble.
  const blocks: (ReplyBlock | AttachmentBlock)[] = assistant
    ? splitMedia(item.text)
    : splitAttachments(item.text);
  const bubble = (
    <div className={`bubble ${item.kind}`} data-testid={`message-${item.kind}`}>
      {/* Your own messages need no name on screen — the side they sit on says it — but a
          screen reader reading the thread in order still needs to hear who spoke. */}
      {assistant ? (
        <Speaker id={agentId} name={speaker} model={item.model} />
      ) : (
        <span className="sr-only">{vi.you}</span>
      )}
      {blocks.map((block, i) =>
        block.kind === "attachment" ? (
          <AttachmentChip key={i} agentId={agentId} path={block.value} />
        ) : block.kind === "canvas" ? (
          <CanvasRefChip key={i} id={block.id} line={block.line} canvas={canvas} />
        ) : block.kind === "media" ? (
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
      {assistant && item.text.trim() !== "" && <BubbleActions text={item.text} />}
      {!assistant && onFork && <ForkButton onClick={() => onFork(item)} />}
    </div>
  );
  // The canvas note a message carried hangs under its bubble, not inside it: the bubble's
  // colour is the person's own words, and the note is the document's.
  return item.kind === "user" && item.context ? (
    <>
      {bubble}
      <CanvasNoteChip note={item.context} />
    </>
  ) : (
    bubble
  );
}
