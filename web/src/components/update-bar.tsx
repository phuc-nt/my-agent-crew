import { vi } from "../i18n/vi";
import { Icon } from "./ui/icon";

interface Props {
  /** Loads the page again; a test passes its own, since jsdom cannot navigate. */
  onReload?: () => void;
}

/**
 * Says the server runs a newer build than this page, and offers to load it.
 *
 * It floats over the top of whichever screen is showing rather than taking a row of its
 * own: the screens fill the viewport exactly, and a row pushed in above them would make
 * the whole page scroll. It asks rather than reloading by itself, since a reload would
 * throw away a reply being read or a message half written.
 */
export function UpdateBar({ onReload = () => window.location.reload() }: Props) {
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
    </div>
  );
}
