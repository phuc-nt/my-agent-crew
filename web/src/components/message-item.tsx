import { agentFileUrl } from "../api/client";
import { vi } from "../i18n/vi";
import type { FramePaths } from "../lib/desktop-frame";
import { type ReplyBlock, splitMedia } from "../lib/reply-blocks";
import { splitScriptHandoff } from "../lib/script-handoff";
import type { ThreadItem } from "../state/thread-reducer";
import { AttachmentChip, fileName, splitAttachments, type AttachmentBlock } from "./attachment-chip";
import type { CanvasLinks } from "./canvas/canvas-card";
import { CanvasNoteChip } from "./canvas/canvas-note-chip";
import { CanvasRefChip } from "./canvas/canvas-ref-chip";
import { BubbleActions } from "./copy-button";
import { ForkButton } from "./fork-button";
import { MarkdownBody } from "./markdown-body";
import { ScriptPrinted } from "./script-printed";
import { ToolCallCard } from "./tool-call-card";
import { AgentAvatar } from "./ui/agent-avatar";
import { Icon } from "./ui/icon";

/** Who said the reply: the agent's tile and name, and the model that wrote it when known. */
export function Speaker({ id, name, model }: { id: string; name: string; model?: string | null }) {
  return (
    <span className="bubble-role">
      <AgentAvatar id={id} name={name} size="sm" />
      <span className="speaker-name">{name}</span>
      {model && <span className="muted speaker-model"> · {model}</span>}
    </span>
  );
}

export function Item({
  item,
  agentId,
  frames,
  speaker,
  agentName,
  onOpenConversation,
  canvas,
  onFork,
}: {
  item: ThreadItem;
  agentId: string;
  /** The desktop pictures the thread's screenshots saved, by frame. */
  frames?: FramePaths;
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
      <ToolCallCard
        item={item}
        agentId={agentId}
        frames={frames}
        agentName={agentName}
        onOpenConversation={onOpenConversation}
        canvas={canvas}
      />
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
  const handed = item.kind === "user" ? splitScriptHandoff(item.text) : null;
  const blocks: (ReplyBlock | AttachmentBlock)[] = assistant ? splitMedia(item.text) : splitAttachments(handed?.prompt ?? item.text);
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
  // colour is the person's own words, and the note is the document's. So does what a script printed.
  return (
    <>
      {bubble}
      {handed && <ScriptPrinted text={handed.printed} />}
      {item.kind === "user" && item.context && <CanvasNoteChip note={item.context} />}
    </>
  );
}
