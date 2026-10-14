import { useState } from "react";
import { agentFileUrl } from "../api/client";
import { useFolderPath } from "../hooks/use-frame-picture";
import { vi } from "../i18n/vi";
import { type FramePaths, frameSize, savedShot, unchangedFrame } from "../lib/desktop-frame";

interface Props {
  /** Whose workspace the picture is in. Without it there is nowhere to ask for the file. */
  agentId?: string;
  toolName: string;
  /** What the call answered, or the line a run's step keeps of it. */
  output: string | null | undefined;
  /** The pictures the screenshots beside this one saved, by frame. */
  frames?: FramePaths;
}

/**
 * The picture `computer_screenshot` saved, small, as the way to the whole of it in a tab of
 * its own.
 *
 * A screen unchanged since the last picture names only its frame: that frame's picture is the
 * one a screenshot beside it saved, else the one in the agent's folder. A line that reads as
 * neither shows nothing, and so does a picture that does not load, removed since or out of
 * reach.
 */
export function DesktopShotThumb({ agentId, toolName, output, frames }: Props) {
  // The path that failed, not a flag: a row that comes to name another picture tries that one.
  const [failed, setFailed] = useState<string | null>(null);
  const saved = savedShot(toolName, output);
  const unchanged = saved ? null : unchangedFrame(toolName, output);
  const beside = unchanged ? (frames?.get(unchanged) ?? null) : null;
  const folder = useFolderPath(agentId, unchanged && !beside ? unchanged : null);
  const frame = saved?.frame ?? unchanged;
  const path = saved?.path ?? beside ?? folder;
  if (!agentId || !frame || !path || path === failed) return null;
  const size = frameSize(frame);
  const url = agentFileUrl(agentId, path);
  return (
    <a className="screenshot-thumb" data-testid="screenshot-thumb" href={url} target="_blank" rel="noreferrer">
      <img
        src={url}
        alt={vi.desktop.screenshotAlt(size?.width ?? 0, size?.height ?? 0)}
        loading="lazy"
        onError={() => setFailed(path)}
      />
    </a>
  );
}
