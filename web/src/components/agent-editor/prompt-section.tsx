import { useState } from "react";
import { api } from "../../api/client";
import { vi } from "../../i18n/vi";
import { CopyButton } from "../copy-button";

interface Props {
  agentId: string;
}

/**
 * What the agent is actually told, assembled by the server from the same code a turn uses.
 *
 * Loaded on demand rather than with the rest of the form: it is the largest thing on the
 * screen and the one least often read, and every section above it is what changes it.
 * Re-fetched on each open so it reflects a persona file saved a moment ago.
 */
export function PromptSection({ agentId }: Props) {
  const [prompt, setPrompt] = useState<string | null>(null);
  const [chars, setChars] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const open = async () => {
    setLoading(true);
    setError("");
    try {
      const got = await api.agentPrompt(agentId);
      setPrompt(got.prompt);
      setChars(got.chars);
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
            if (prompt === null) void open();
            else setPrompt(null);
          }}
        >
          {loading ? vi.manage.loading : prompt === null ? vi.editor.promptShow : vi.editor.promptHide}
        </button>
        {prompt !== null && (
          <>
            <span className="muted">{vi.editor.promptChars(chars)}</span>
            {/* Mounted with each read, so a new read never starts out saying it was copied. */}
            <CopyButton text={prompt} label={vi.copy.prompt} />
          </>
        )}
      </div>
      {prompt !== null && (
        <pre className="prompt-preview" data-testid="prompt-preview">
          {prompt}
        </pre>
      )}
    </section>
  );
}
