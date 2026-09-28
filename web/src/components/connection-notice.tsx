import { useOnline } from "../hooks/use-online";
import { vi } from "../i18n/vi";

interface Props {
  connected: boolean;
  /** The stream was just (re)opened: not yet live, but not lost either. */
  connecting: boolean;
  /** Opens the live stream again. */
  onRetry: () => void;
}

/**
 * Says when the pages of the manage screen stopped following the server. Their lists and
 * counts come from the live stream, so once it drops they go stale with nothing to show
 * it; the chat has its status line for this, the manage screen has this notice. The live
 * region stays in place while empty, so a screen reader hears the sentence as it appears;
 * it is no status role, which the pages keep for their own notices.
 */
export function ConnectionNotice({ connected, connecting, onRetry }: Props) {
  const online = useOnline();
  const lost = !connected && !connecting;
  return (
    <div className="connection-status" aria-live="polite" data-testid="connection-status">
      {!online ? (
        <p className="notice warn">{vi.manage.offline}</p>
      ) : (
        lost && (
          <p className="notice warn">
            {vi.manage.disconnected}
            <button type="button" className="link-button" aria-label={vi.streamRetryLabel} onClick={onRetry}>
              {vi.retry}
            </button>
          </p>
        )
      )}
    </div>
  );
}
