import { useState } from "react";
import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { dayClock } from "../lib/relative-time";
import { splitMedia } from "../lib/reply-blocks";
import { jobName } from "../state/inbox";
import { MarkdownBody } from "./markdown-body";
import { AgentAvatar } from "./ui/agent-avatar";

/** Past this a report opens folded, so one long brief does not push the rest off the screen. */
const LONG_CHARS = 700;
const LONG_LINES = 14;

interface Props {
  run: RunInfo;
  /** What the run sent to the chat, whole; its summary until that is read. */
  text: string;
  agent: string;
  fresh: boolean;
  onOpen: (run: RunInfo) => void;
}

/**
 * One job's report as the chat is sent it: under the agent's name, the job and when, then
 * its words, formatted, read where they are listed. A picture or a file the report sends is
 * named, not drawn, and is in its conversation, which is also where it is answered.
 */
export function InboxReport({ run, text, agent, fresh, onOpen }: Props) {
  const [open, setOpen] = useState(false);
  const at = dayClock(run.finished_at ?? run.started_at);
  const job = jobName(run.title) || agent;
  const blocks = splitMedia(text);
  const prose = blocks.flatMap((b) => (b.kind === "text" && b.value.trim() ? [b.value] : []));
  const sent = blocks.length - blocks.filter((b) => b.kind === "text").length;
  const long = text.length > LONG_CHARS || text.split("\n").length > LONG_LINES;

  return (
    <article className={`inbox-report${fresh ? " fresh" : ""}`} aria-label={vi.inbox.resultLabel(job, agent, at)}>
      <header className="inbox-report-head">
        <AgentAvatar id={run.agent_id} name={agent} size="sm" />
        <span className="inbox-report-who">
          <span className="inbox-report-agent">{agent}</span>
          <span className="muted inbox-report-job">{job}</span>
        </span>
        {fresh && <span className="badge live inbox-unread">{vi.inbox.unread}</span>}
        <span className="muted tabular inbox-report-at">{at}</span>
      </header>
      <div className={`inbox-report-body${long && !open ? " folded" : ""}`}>
        {prose.map((part, n) => (
          <MarkdownBody key={n} text={part} />
        ))}
        {sent > 0 && <p className="muted inbox-report-sent">{vi.inbox.sent(sent)}</p>}
      </div>
      <footer className="inbox-report-foot">
        {long && (
          <button type="button" className="link-button" aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? vi.inbox.fold : vi.inbox.unfold}
          </button>
        )}
        <button
          type="button"
          className="inbox-report-open"
          aria-label={vi.inbox.openReport(job)}
          onClick={() => onOpen(run)}
        >
          {vi.inbox.reply}
        </button>
      </footer>
    </article>
  );
}
