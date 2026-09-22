import { useState } from "react";
import { api } from "../../api/client";
import { vi } from "../../i18n/vi";

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
  const [copied, setCopied] = useState(false);

  const open = async () => {
    setLoading(true);
    setError("");
    // A fresh read is fresh text, so a "copied" from the previous one no longer describes
    // what is on screen.
    setCopied(false);
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

  const copy = async () => {
    if (prompt === null) return;
    try {
      await navigator.clipboard.writeText(prompt);
      setCopied(true);
    } catch {
      // A browser that refuses the clipboard still shows the text to select by hand.
      setError(vi.editor.promptFailed);
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
      <div className="row">
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
            <button type="button" className="ghost" onClick={() => void copy()}>
              {copied ? vi.editor.promptCopied : vi.editor.promptCopy}
            </button>
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
