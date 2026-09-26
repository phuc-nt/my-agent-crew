import { useId, useState } from "react";
import { vi } from "../i18n/vi";

/** The arguments a person reads as text, line by line: a shell command, a file body, a diff.
 *  Quoted inside JSON they would lose their line breaks to "\n" and become unreadable. */
const TEXT_KEYS = ["command", "content", "patch"];

/** Past this length the one-line summary cuts a value, so the full view has more to say. */
export const SUMMARY_CUT = 60;

type Args = Record<string, unknown> | string;

/** Whether the one-line summary already shows everything; if so the disclosure would
 *  only repeat it, and a link that opens nothing new teaches people to skip it. */
function hasMore(args: Args): boolean {
  if (typeof args === "string") return args.includes("\n");
  return Object.values(args).some((value) => {
    if (value !== null && typeof value === "object") return true;
    const text = typeof value === "string" ? value : JSON.stringify(value) ?? "";
    return text.length > SUMMARY_CUT || text.includes("\n");
  });
}

/** Splits the arguments into the text blocks and whatever is left, shown as JSON. */
function parts(args: Args): { text: [string, string][]; rest: Record<string, unknown> | null } {
  // Rows stored before arguments were a mapping hold one line; it is text as it stands.
  if (typeof args === "string") return { text: [["", args]], rest: null };
  const text: [string, string][] = [];
  const rest: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(args)) {
    if (TEXT_KEYS.includes(key) && typeof value === "string") text.push([key, value]);
    else rest[key] = value;
  }
  return { text, rest: Object.keys(rest).length > 0 ? rest : null };
}

/**
 * The whole of a tool call's arguments, behind a "Xem đầy đủ" disclosure. The summary line
 * cuts each value at sixty characters, which is enough to recognise a call and not enough
 * to judge one: approving a command means reading all of it, not its first words.
 */
export function ToolArgsDetail({ args }: { args: Args }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  if (!hasMore(args)) return null;
  const { text, rest } = parts(args);
  return (
    <div className="args-detail">
      <button
        type="button"
        className="link-button args-detail-toggle"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
      >
        {open ? vi.argumentsLess : vi.argumentsMore}
      </button>
      {open && (
        <div id={id} className="args-detail-body" data-testid="args-detail">
          {text.map(([key, value]) => (
            <div key={key} className="args-detail-field">
              {key && <span className="args-detail-key">{key}</span>}
              <pre className="args-detail-code">{value}</pre>
            </div>
          ))}
          {rest && <pre className="args-detail-code">{JSON.stringify(rest, null, 2)}</pre>}
        </div>
      )}
    </div>
  );
}
