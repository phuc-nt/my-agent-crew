import { useState } from "react";
import type { McpServerInfo, McpStatus, McpToolInfo } from "../api/types";
import type { McpController } from "../hooks/use-mcp-servers";
import { vi } from "../i18n/vi";
import { errorText } from "../lib/error-text";

const STATUS_TONE: Record<McpStatus, "ok" | "warn" | "danger"> = {
  connected: "ok",
  idle: "warn",
  signed_out: "warn",
  failed: "danger",
};

type Action = "reconnect" | "signIn" | "signOut";

function ToolRow({ tool }: { tool: McpToolInfo }) {
  const t = vi.mcp;
  return (
    <li data-testid={`mcp-tool-${tool.remote}`}>
      <div className="mcp-tool-head">
        <code>{tool.remote}</code>
        <span className="badge" title={t.exposureTitle[tool.exposure]}>
          {t.exposure[tool.exposure]}
        </span>
        <span className={`badge ${tool.requires_approval ? "warn" : "ok"}`}>
          {tool.requires_approval ? t.asksFirst : t.runsFreely}
        </span>
        {tool.read_only_hint && (
          <span className="badge" title={t.saysReadOnlyTitle}>
            {t.saysReadOnly}
          </span>
        )}
      </div>
      {tool.description && <div className="muted">{tool.description}</div>}
    </li>
  );
}

/**
 * One server: whether the crew reaches it, why not, who uses it and what it offers. The
 * state shown is the server's own row, read again after every action, so a reconnect that
 * changed nothing shows the reason it failed rather than a note that it was tried.
 */
function ServerRow({ server, mcp }: { server: McpServerInfo; mcp: McpController }) {
  const t = vi.mcp;
  // Which action is in flight: every control waits for it, only its own says so.
  const [pending, setPending] = useState<Action | null>(null);
  const [note, setNote] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);
  const busy = pending !== null;

  const run = async (kind: Action, work: () => Promise<void>, done?: string) => {
    setPending(kind);
    setNote(null);
    try {
      await work();
      if (done) setNote({ tone: "ok", text: done });
    } catch (e) {
      setNote({ tone: "danger", text: vi.connectionsPage.failed(errorText(e)) });
    } finally {
      setPending(null);
    }
  };

  const signOut = () => {
    if (!window.confirm(t.confirmSignOut(server.name))) return;
    void run("signOut", () => mcp.signOut(server.name), t.signedOut);
  };

  return (
    <li className="mcp-server" data-testid={`mcp-server-${server.name}`}>
      <div className="mcp-server-head">
        <code>{server.name}</code>
        <span className={`badge ${STATUS_TONE[server.status]}`} data-testid="mcp-status" role="status">
          {t.status[server.status]}
        </span>
        {server.signed_in && <span className="badge ok">{t.signedIn}</span>}
        {server.uses_key && <span className="badge">{t.usesKey}</span>}
      </div>
      {server.description && <p className="muted">{server.description}</p>}
      <p className="muted mcp-server-url">{server.url}</p>
      {server.error && (
        <p className="credential-note danger" data-testid="mcp-error">
          {server.error}
        </p>
      )}
      {server.status === "signed_out" && <p className="muted">{t.signInHint}</p>}
      <p className="muted" data-testid="mcp-agents">
        {server.agents.length > 0 ? vi.connectionsPage.usedBy(server.agents.join(", ")) : t.noAgents}
      </p>
      {server.tools.length > 0 && (
        <details className="mcp-tools">
          <summary>{t.tools(server.tools.length)}</summary>
          <ul>
            {server.tools.map((tool) => (
              <ToolRow key={tool.name} tool={tool} />
            ))}
          </ul>
        </details>
      )}
      {server.skipped.length > 0 && <p className="warn-text">{t.skipped(server.skipped.join(", "))}</p>}
      <div className="credential-actions">
        {server.status === "signed_out" && (
          <button
            type="button"
            className="primary"
            disabled={busy}
            onClick={() => void run("signIn", () => mcp.signIn(server.name))}
          >
            {pending === "signIn" ? t.signingIn : t.signIn}
          </button>
        )}
        <button type="button" disabled={busy} onClick={() => void run("reconnect", () => mcp.reconnect(server.name))}>
          {pending === "reconnect" ? t.reconnecting : t.reconnect}
        </button>
        {server.signed_in && (
          <button type="button" className="danger" disabled={busy} onClick={signOut}>
            {pending === "signOut" ? t.signingOut : t.signOut}
          </button>
        )}
      </div>
      {note && (
        <p className={`credential-note ${note.tone}`} role="status" data-testid="mcp-note">
          {note.text}
        </p>
      )}
    </li>
  );
}

/** The servers `config.yaml` declares. They are added and removed in that file, so the
 *  card only says how to when there is none. */
export function McpServerList({ mcp }: { mcp: McpController }) {
  const t = vi.mcp;
  if (mcp.error && mcp.servers.length === 0) {
    return (
      <p className="credential-note danger" role="status">
        {t.loadFailed(mcp.error)}
      </p>
    );
  }
  if (mcp.servers.length === 0) return <p className="muted">{t.empty}</p>;
  return (
    <ul className="mcp-servers" data-testid="mcp-servers">
      {mcp.servers.map((server) => (
        <ServerRow key={server.name} server={server} mcp={mcp} />
      ))}
    </ul>
  );
}
