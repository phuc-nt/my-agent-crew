import { type CSSProperties, useState } from "react";
import { agentFileUrl } from "../api/client";
import { useApprovalFrame } from "../hooks/use-frame-picture";
import { vi } from "../i18n/vi";
import { ACT_TOOL } from "../lib/desktop-call";
import { frameSize, isFrame } from "../lib/desktop-frame";
import { formatDateTime } from "./run-timeline";

interface Props {
  /** The conversation the call waits in: its screenshots say where the frame's picture is. */
  conversationId?: string;
  name: string;
  args: unknown;
}

interface Mark {
  x: number;
  y: number;
  label: string;
}

type Args = Record<string, unknown>;

const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);

/** The points an action names on its frame: one for a click or a scroll by point, two for a
 *  drag. A call by ref names an element and no point, and a point off the picture marks
 *  nothing. */
export function framePoints(args: Args, width: number, height: number): Mark[] {
  if (typeof args.ref === "string" && args.ref !== "") return [];
  const t = vi.desktop.frame;
  const at = (x: unknown, y: unknown, label: string): Mark[] =>
    finite(x) && finite(y) && x >= 0 && y >= 0 && x <= width && y <= height ? [{ x, y, label }] : [];
  switch (args.kind) {
    case "click":
    case "double_click":
    case "right_click":
    case "scroll":
      return at(args.x, args.y, t.point);
    case "drag":
      return [...at(args.x, args.y, t.point), ...at(args.to_x, args.to_y, t.dropPoint)];
    default:
      return [];
  }
}

/**
 * The picture a waiting desktop action was chosen on, with the point it acts at marked, and
 * when that picture was taken.
 *
 * It is what the agent saw, not the screen as it is while the card waits, so the time is said
 * under it. A frame id that is not one, a picture no longer kept, or a conversation that cannot
 * be read leaves the card without it: the call is still read in words above and in full below.
 */
export function DesktopFrameThumb({ conversationId, name, args }: Props) {
  const fields = name === ACT_TOOL && typeof args === "object" && args !== null ? (args as Args) : null;
  const frame = fields && isFrame(fields.frame_id) ? fields.frame_id : null;
  const picture = useApprovalFrame(conversationId, frame);
  const [failed, setFailed] = useState<string | null>(null);
  if (!fields || !frame || !picture || picture.path === failed) return null;
  const size = frameSize(frame);
  const url = agentFileUrl(picture.agentId, picture.path);
  const marks = size ? framePoints(fields, size.width, size.height) : [];
  const t = vi.desktop.frame;
  return (
    <figure className="desktop-frame" data-testid="desktop-frame">
      <a
        className="desktop-frame-picture"
        style={size ? ({ "--frame-ratio": String(size.width / size.height) } as CSSProperties) : undefined}
        href={url}
        target="_blank"
        rel="noreferrer"
      >
        <img src={url} alt={t.alt(size?.width ?? 0, size?.height ?? 0)} onError={() => setFailed(picture.path)} />
        {size &&
          marks.map((mark, at) => (
            <span
              key={at}
              className={`desktop-frame-point${at > 0 ? " drop" : ""}`}
              style={{ left: `${(mark.x / size.width) * 100}%`, top: `${(mark.y / size.height) * 100}%` }}
              title={mark.label}
              aria-hidden="true"
              data-testid="desktop-frame-point"
            />
          ))}
      </a>
      {picture.takenAt && (
        <figcaption className="muted" data-testid="desktop-frame-time">
          {t.takenAt(formatDateTime(picture.takenAt))}
        </figcaption>
      )}
    </figure>
  );
}
