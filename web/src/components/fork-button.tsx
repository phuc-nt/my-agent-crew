import { vi } from "../i18n/vi";
import { Icon } from "./ui/icon";

/**
 * "Sửa và gửi lại từ đây": rewinds and forks the conversation at the user message this
 * button sits under. Only ever rendered on a user bubble — see `message-thread.tsx`'s
 * `Item`, which never passes it an assistant or tool item.
 *
 * Styled apart from `.copy-button` (see `thread-composer.css`): that button uses
 * `--muted`, which reads too faint over the coloured user bubble, so this one uses the
 * bubble's own text colour instead. It sits bare in the bubble rather than inside a
 * `.bubble-actions` row, so it reveals on `:hover`/`:focus-visible` directly rather than
 * through a wrapping container — same occasions as `.bubble-actions`, just addressed
 * without one, and always visible under `@media (hover: none)` the same way.
 */
export function ForkButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      className="fork-button"
      aria-label={vi.fork.fromHere}
      title={vi.fork.fromHere}
      onClick={onClick}
    >
      <Icon name="edit" />
    </button>
  );
}
