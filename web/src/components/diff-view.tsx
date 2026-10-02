import { vi } from "../i18n/vi";
import type { CanvasDiffLine } from "../lib/canvas-diff";
import { showHiddenChars } from "../lib/hidden-chars";
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

/**
 * Two canvas versions from `canvasDiff`: a long unchanged run is a count between its edges,
 * and hidden characters show as marks, so a change made only of them can be seen.
 */
export function CanvasDiffView({ lines }: { lines: CanvasDiffLine[] | null }) {
  if (lines === null) return <p className="muted">{vi.canvas.tooBig}</p>;
  if (lines.length === 0) return <p className="muted">{vi.canvas.noChange}</p>;
  return (
    <pre className="diff canvas-diff">
      {lines.map((line, index) =>
        line.op === "skip" ? (
          <div key={index} className="skipped">
            {vi.canvas.unchanged(line.count)}
          </div>
        ) : (
          <div key={index} className={CLASS[line.op]}>
            {PREFIX[line.op]}
            {showHiddenChars(line.text)}
          </div>
        ),
      )}
    </pre>
  );
}
