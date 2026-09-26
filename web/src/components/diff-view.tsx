import { vi } from "../i18n/vi";
import { lineDiff } from "../lib/line-diff";

const PREFIX = { same: "  ", add: "+ ", remove: "- " } as const;
const CLASS = { same: "", add: "added", remove: "removed" } as const;

/**
 * Two versions of a text, line by line: kept lines as context, removed ones in red, new
 * ones in green. The `+`/`-` prefix carries the meaning too, so the colour is never the
 * only way to tell a line that goes from one that arrives.
 */
export function DiffView({ before, after }: { before: string; after: string }) {
  const lines = lineDiff(before, after);
  if (!lines.some((line) => line.op !== "same")) {
    return <p className="muted">{vi.memory.diffNone}</p>;
  }
  return (
    <pre className="diff">
      {lines.map((line, index) => (
        <div key={index} className={CLASS[line.op]}>
          {PREFIX[line.op]}
          {line.text}
        </div>
      ))}
    </pre>
  );
}
