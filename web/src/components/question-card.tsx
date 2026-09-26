import { useState } from "react";
import { vi } from "../i18n/vi";
import { type PendingApproval, questionText } from "../state/thread-reducer";
import { formatClock } from "./run-timeline";
import { Icon } from "./ui/icon";

interface Props {
  pending: PendingApproval;
  busy: boolean;
  onAnswer: (text: string) => void;
}

/** What the agent asked, and somewhere to reply.
 *
 * A question is not an approval. The tool card's Allow/Refuse buttons close a request to
 * run something; here there is nothing to authorise, only something the agent cannot find
 * out by itself. The offered choices are buttons because that is the fast path, but the
 * text box stays open: the server takes any wording, and a question worth asking often has
 * an answer nobody listed. */
export function QuestionCard({ pending, busy, onAnswer }: Props) {
  const [text, setText] = useState("");
  const asked = questionText(pending);
  const submit = () => {
    const answer = text.trim();
    if (answer) onAnswer(answer);
  };

  return (
    <div className="question-card callout" role="alertdialog" aria-label={vi.awaitingAnswer}>
      <div className="question-text">
        <strong>
          <Icon name="help" className="callout-inline-icon" />
          {vi.questionTitle}
        </strong>
        <p className="question-asked">{asked || pending.name}</p>
        {pending.expiresAt && (
          <span className="approval-deadline">{vi.questionDeadline(formatClock(pending.expiresAt))}</span>
        )}
      </div>
      {pending.options.length > 0 && (
        <div className="question-options">
          {pending.options.map((option) => (
            <button key={option} type="button" disabled={busy} onClick={() => onAnswer(option)}>
              {option}
            </button>
          ))}
        </div>
      )}
      <form
        className="question-form"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <input
          type="text"
          value={text}
          disabled={busy}
          aria-label={vi.questionPlaceholder}
          placeholder={vi.questionPlaceholder}
          onChange={(e) => setText(e.target.value)}
        />
        <button type="submit" className="primary" disabled={busy || !text.trim()}>
          {vi.questionSend}
        </button>
      </form>
    </div>
  );
}
