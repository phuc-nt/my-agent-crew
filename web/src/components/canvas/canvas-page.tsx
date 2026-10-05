/**
 * One canvas on a page of its own, in the panel a conversation shows it in, with the conversations
 * it is used in named under it.
 *
 * The page belongs to no conversation, so the panel is given nothing to ask an agent with. Leaving
 * is never held up: every way out of the panel is the way back, and the panel hands its last save
 * on as it goes, to be said in the section's notices if it fails.
 */

import type { Conversation } from "../../api/types";
import type { CanvasDock } from "../../hooks/use-canvas-dock";
import { useCanvasConversations } from "../../hooks/use-canvas-conversations";
import { vi } from "../../i18n/vi";
import { CanvasPanel } from "./canvas-panel";

const { canvas } = vi;

type Props = {
  /** The canvas to show: an id the server could have given, checked by whoever read the address. */
  id: string;
  connected: boolean;
  /** What a dock lends the panel so a save can be asked for and its trouble said. */
  dock: Pick<CanvasDock, "stuck" | "bind" | "flush">;
  agentName: (id: string) => string;
  /** The conversations this tab has listed, for their names. */
  conversations: Conversation[];
  onBack(): void;
  onOpenConversation(id: string): void;
};

export function CanvasPage({ id, connected, dock, agentName, conversations, onBack, onOpenConversation }: Props) {
  const usedIn = useCanvasConversations(id, connected);
  return (
    <div className="canvas-page">
      {/* Keyed by the canvas: the next one starts from nothing of this one's. */}
      <CanvasPanel
        key={id}
        artifactId={id}
        created={false}
        connected={connected}
        stuck={dock.stuck}
        agentName={agentName}
        bind={dock.bind}
        flush={dock.flush}
        onShowList={onBack}
        onClose={onBack}
        onForceClose={onBack}
      />
      {usedIn.length > 0 && (
        <p className="muted canvas-page-used">
          <span>{canvas.usedIn(usedIn.length)}</span>
          {usedIn.map((conversationId) => (
            <button
              key={conversationId}
              type="button"
              className="link-button"
              onClick={() => onOpenConversation(conversationId)}
            >
              {conversations.find((each) => each.id === conversationId)?.title ||
                canvas.conversationFallback(conversationId)}
            </button>
          ))}
        </p>
      )}
    </div>
  );
}
