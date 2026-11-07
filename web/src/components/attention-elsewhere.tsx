import { vi } from "../i18n/vi";
import { Icon } from "./ui/icon";

export interface Elsewhere {
  /** Requests waiting in another section, so the card never says there is nothing. */
  waitingElsewhere?: number;
  onOpenWaiting?: () => void;
  /** Failures not yet read, listed in another section — the same promise the other way. */
  failedElsewhere?: number;
  onOpenFailed?: () => void;
  /** Rewrites of an agent's memory held for the person, decided on the memory page. */
  proposalsElsewhere?: number;
  onOpenProposals?: () => void;
}

/** How much waits on the person outside the list: none of it may be read as "nothing". */
export function elsewhereCount(props: Elsewhere): number {
  return (props.waitingElsewhere ?? 0) + (props.failedElsewhere ?? 0) + (props.proposalsElsewhere ?? 0);
}

/** One button per section that holds work for the person, each saying how much. */
export function AttentionElsewhere(props: Elsewhere) {
  const links: [number, string, (() => void) | undefined][] = [
    [props.waitingElsewhere ?? 0, vi.attentionWaitingElsewhere(props.waitingElsewhere ?? 0), props.onOpenWaiting],
    [props.failedElsewhere ?? 0, vi.attentionFailedElsewhere(props.failedElsewhere ?? 0), props.onOpenFailed],
    [props.proposalsElsewhere ?? 0, vi.attentionProposals(props.proposalsElsewhere ?? 0), props.onOpenProposals],
  ];
  return links
    .filter(([count]) => count > 0)
    .map(([, text, onClick]) => (
      <button key={text} type="button" className="attention-elsewhere" onClick={onClick}>
        {text}
        <Icon name="arrow-right" />
      </button>
    ));
}
