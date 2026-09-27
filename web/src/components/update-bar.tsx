import { vi } from "../i18n/vi";
import { Icon } from "./ui/icon";

interface Props {
  /** Loads the page again; a test passes its own, since jsdom cannot navigate. */
  onReload?: () => void;
  /** Puts the bar away for now, to reload later. */
  onDismiss: () => void;
}

/**
 * Says the server runs a newer build than this page, and offers to load it.
 *
 * It floats over the top of whichever screen is showing rather than taking a row of its
 * own: the screens fill the viewport exactly, and a row pushed in above them would make
 * the whole page scroll. It asks rather than reloading by itself, since a reload would
 * throw away a reply being read or a message half written — and floating, it covers the
 * top of the screen, so it can be put away while that reply or message is finished.
 */
export function UpdateBar({ onReload = () => window.location.reload(), onDismiss }: Props) {
  return (
    <div className="update-bar" role="status" data-testid="update-bar">
      <span>{vi.updateAvailable}</span>
      <button
        type="button"
        className="primary update-bar-reload"
        aria-label={vi.updateReloadLabel}
        onClick={onReload}
      >
        <Icon name="refresh" />
        {vi.reload}
      </button>
      <button type="button" className="icon-button update-bar-dismiss" aria-label={vi.updateDismissLabel} onClick={onDismiss}>
        <Icon name="close" />
      </button>
    </div>
  );
}
