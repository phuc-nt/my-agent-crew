import { useEffect, useRef } from "react";
import { vi } from "../i18n/vi";
import type { ThreadItem } from "../state/thread-reducer";
import { ToolCallCard } from "./tool-call-card";

interface Props {
  items: ThreadItem[];
  streaming: string | null;
  busy: boolean;
  onSuggestion: (text: string) => void;
  echoOnly: boolean;
}

export function MessageThread({ items, streaming, busy, onSuggestion, echoOnly }: Props) {
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: "end" });
  }, [items.length, streaming]);

  if (items.length === 0 && !streaming) {
    return (
      <section className="thread empty-state" aria-label={vi.agent}>
        <h2>{vi.welcomeTitle}</h2>
        <p>{vi.welcomeBody}</p>
        <div className="suggestions">
          {vi.welcomeSuggestions.map((s) => (
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
        <Item key={item.id} item={item} />
      ))}
      {streaming !== null && (
        <div className="bubble assistant streaming" data-testid="streaming">
          <span className="bubble-role">{vi.agent}</span>
          <p>{streaming}</p>
        </div>
      )}
      {busy && streaming === null && (
        <div className="thinking" data-testid="thinking">
          {vi.thinking}
        </div>
      )}
      <div ref={bottom} />
    </section>
  );
}

function Item({ item }: { item: ThreadItem }) {
  if (item.kind === "tool") return <ToolCallCard item={item} />;
  const role = item.kind === "user" ? vi.you : vi.agent;
  return (
    <div className={`bubble ${item.kind}`} data-testid={`message-${item.kind}`}>
      <span className="bubble-role">
        {role}
        {item.kind === "assistant" && item.model && <span className="muted"> · {item.model}</span>}
      </span>
      <p>{item.text}</p>
    </div>
  );
}
