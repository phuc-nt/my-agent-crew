import { useEffect, useRef } from "react";
import { agentFileUrl } from "../api/client";
import type { RunInfo } from "../api/types";
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
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: "end" });
  }, [items.length, streaming]);

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
    <section className="thread" aria-live="polite">
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
      <div ref={bottom} />
    </section>
  );
}

/** Splits a reply into text blocks and `MEDIA:<path>` lines, which become inline images. */
export function splitMedia(text: string): { kind: "text" | "media"; value: string }[] {
  const blocks: { kind: "text" | "media"; value: string }[] = [];
  const pending: string[] = [];
  const flush = () => {
    if (pending.length > 0) blocks.push({ kind: "text", value: pending.join("\n") });
    pending.length = 0;
  };
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (trimmed.startsWith(MEDIA_PREFIX) && trimmed.length > MEDIA_PREFIX.length) {
      flush();
      blocks.push({ kind: "media", value: trimmed.slice(MEDIA_PREFIX.length).trim() });
    } else {
      pending.push(line);
    }
  }
  flush();
  return blocks;
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
        ) : assistant ? (
          <MarkdownBody key={i} text={block.value} />
        ) : (
          <p key={i}>{block.value}</p>
        ),
      )}
    </div>
  );
}
