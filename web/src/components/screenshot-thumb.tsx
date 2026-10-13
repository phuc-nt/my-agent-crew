import { useState } from "react";
import { agentFileUrl } from "../api/client";
import { vi } from "../i18n/vi";
import { screenshotLabel, screenshotPath } from "../lib/screenshot-path";

interface Props {
  /** Whose workspace the picture is in. Without it there is nowhere to ask for the file. */
  agentId?: string;
  toolName: string;
  /** What the call answered, or the line a run's step keeps of it. */
  output: string | null | undefined;
}

/**
 * The picture `browser_screenshot` saved, small, as the way to the whole of it in a tab of
 * its own.
 *
 * Whether the call succeeded is the caller's to say: a refused or failed call names no file
 * worth asking for. A picture that does not load, removed since or out of reach, leaves
 * nothing behind, and the row reads as it did before there were pictures.
 */
export function ScreenshotThumb({ agentId, toolName, output }: Props) {
  // The path that failed, not a flag: a row that comes to name another picture tries that one.
  const [failed, setFailed] = useState<string | null>(null);
  const path = agentId ? screenshotPath(toolName, output) : null;
  if (!agentId || path === null || path === failed) return null;
  const url = agentFileUrl(agentId, path);
  return (
    <a className="screenshot-thumb" data-testid="screenshot-thumb" href={url} target="_blank" rel="noreferrer">
      <img
        src={url}
        alt={vi.browser.screenshotAlt(screenshotLabel(output ?? ""))}
        loading="lazy"
        onError={() => setFailed(path)}
      />
    </a>
  );
}
