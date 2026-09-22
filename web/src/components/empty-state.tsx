import type { ReactNode } from "react";

interface Props {
  /** What is not here. One sentence, in the person's own terms. */
  says: string;
  /** What to do about it, when there is something. Absent leaves the sentence alone. */
  action?: { label: string; onClick: () => void };
  /** Anything else worth saying under the action, such as where the data comes from. */
  children?: ReactNode;
}

/**
 * A section with nothing in it yet, and the one thing to do about that.
 *
 * Most of these places used to be a bare sentence. "Nothing here" is only half an
 * answer: the person is left to guess whether they are missing a step, waiting on
 * something, or looking in the wrong place. Where a next step exists the button is
 * the answer; where it does not, a plain sentence is still the honest version, so
 * the action is optional rather than invented for the sake of symmetry.
 */
export function EmptyState({ says, action, children }: Props) {
  return (
    <div className="empty" data-testid="empty-state">
      <p className="muted">{says}</p>
      {action && (
        <button type="button" className="chip" onClick={action.onClick}>
          {action.label}
        </button>
      )}
      {children}
    </div>
  );
}
