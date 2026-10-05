import { useState } from "react";
import { api } from "../../api/client";
import { vi } from "../../i18n/vi";
import { CopyButton } from "../copy-button";

interface Props {
  agentId: string;
}

interface Shown {
  prompt: string;
  chars: number;
  opening: string;
  openingChars: number;
}

/**
 * What the agent is actually told, assembled by the server from the same code a turn uses.
 *
 * Loaded on demand rather than with the rest of the form: it is the largest thing on the
 * screen and the one least often read, and every section above it is what changes it.
 * Re-fetched on each open so it reflects a persona file saved a moment ago.
 *
 * The daily notes are no part of the system prompt: a turn reads them in front of the
 * message that opens it. They are shown under the prompt, as what they are, so a note the
 * agent saved is not looked for in the prompt and taken as lost.
 */
export function PromptSection({ agentId }: Props) {
  const [shown, setShown] = useState<Shown | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const open = async () => {
    setLoading(true);
    setError("");
    try {
      const got = await api.agentPrompt(agentId);
      setShown({
        prompt: got.prompt,
        chars: got.chars,
        opening: got.opening,
        openingChars: got.opening_chars,
      });
    } catch {
      setError(vi.editor.promptFailed);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="editor-section" data-testid="section-prompt">
      <h3>{vi.editor.sectionPrompt}</h3>
      <p className="muted">{vi.editor.promptHint}</p>
      {error && (
        <div className="notice error" role="status">
          {error}
        </div>
      )}
      {/* Wraps, so the box a failed copy opens takes a line of its own under the buttons. */}
      <div className="row wrap">
        <button
          type="button"
          className="ghost"
          disabled={loading}
          onClick={() => {
            if (shown === null) void open();
            else setShown(null);
          }}
        >
          {loading ? vi.manage.loading : shown === null ? vi.editor.promptShow : vi.editor.promptHide}
        </button>
        {shown !== null && (
          <>
            <span className="muted">{vi.editor.promptChars(shown.chars)}</span>
            {/* Mounted with each read, so a new read never starts out saying it was copied. */}
            <CopyButton text={shown.prompt} label={vi.copy.prompt} />
          </>
        )}
      </div>
      {shown !== null && (
        <pre className="prompt-preview" data-testid="prompt-preview">
          {shown.prompt}
        </pre>
      )}
      {/* An agent with no notes is told nothing there, and is shown nothing. */}
      {shown !== null && shown.opening !== "" && (
        <div className="prompt-opening">
          <h4>{vi.editor.promptOpening}</h4>
          <p className="muted">{vi.editor.promptOpeningHint}</p>
          <span className="muted">{vi.editor.promptChars(shown.openingChars)}</span>
          <pre className="prompt-preview" data-testid="prompt-opening">
            {shown.opening}
          </pre>
        </div>
      )}
    </section>
  );
}
