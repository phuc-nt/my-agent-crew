import type { QueuedMessage } from "../api/types";
import { vi } from "../i18n/vi";
import { Icon, type IconName } from "./ui/icon";

const KIND_ICON: Record<QueuedMessage["kind"], IconName> = {
  follow_up: "corner-down-right",
  steer: "bolt",
};

const KIND_LABEL: Record<QueuedMessage["kind"], string> = {
  follow_up: vi.queuedFollowUp,
  steer: vi.queuedSteer,
};

interface Props {
  items: QueuedMessage[];
}

/**
 * The chips a message becomes once it finds the conversation busy: confirmation that it
 * was received, nothing more. There is no button here — cancelling one is Stop's job,
 * which clears the whole queue at once (see `docs/design.md`, "Web UI").
 */
export function QueuedChips({ items }: Props) {
  if (items.length === 0) return null;
  return (
    <ul className="queued-chips" aria-live="polite" aria-label={vi.queuedLabel}>
      {items.map((item) => (
        <li key={item.id} className={`queued-chip ${item.kind}`}>
          <Icon name={KIND_ICON[item.kind]} />
          <span className="sr-only">{KIND_LABEL[item.kind]}</span>
          <span className="queued-chip-text">{item.text}</span>
        </li>
      ))}
    </ul>
  );
}
