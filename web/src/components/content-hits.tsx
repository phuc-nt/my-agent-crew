import type { ContentHit } from "../api/types";
import { vi } from "../i18n/vi";
import { timeAgo } from "../lib/relative-time";

interface Props {
  hits: ContentHit[] | null;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
  onSelect: (conversationId: string) => void;
  /** Turns a raw `agent_id` into the name shown on each hit's badge, e.g. `crew.agentName`. */
  agentName: (agentId: string) => string;
  /** What "ngày" is measured from; the sidebar already keeps one clock for every row. */
  now: Date;
}

/**
 * The "Trong nội dung" section under the sidebar's title search: hits found inside
 * message text rather than a conversation's own title. Renders nothing at all once
 * settled with no hits, since the title search above it already covers that empty case.
 */
export function ContentHits({ hits, loading, error, onRetry, onSelect, agentName, now }: Props) {
  if (loading) return <p className="muted content-hits-status">{vi.contentSearch.loading}</p>;
  if (error) {
    return (
      <p className="notice warn content-hits-status">
        {vi.contentSearch.error}
        <button type="button" className="link-button" onClick={onRetry}>
          {vi.retry}
        </button>
      </p>
    );
  }
  if (!hits || hits.length === 0) return null;

  return (
    <div className="content-hits">
      <h2>{vi.contentSearch.heading}</h2>
      <ul>
        {hits.map((hit) => (
          <li key={hit.message_id}>
            <button type="button" onClick={() => onSelect(hit.conversation_id)}>
              <span className="content-hit-title">{hit.title || vi.newConversation}</span>
              <span className="content-hit-agent">{agentName(hit.agent_id)}</span>
              <span className="content-hit-snippet">{hit.snippet}</span>
              <time className="content-hit-time" dateTime={hit.created_at}>
                {timeAgo(hit.created_at, now)}
              </time>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
