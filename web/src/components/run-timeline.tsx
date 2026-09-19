import { useState } from "react";
import type { RunInfo, RunStep } from "../api/types";
import { vi } from "../i18n/vi";
import { formatUsd } from "./budget-indicator";
import { summarizeArguments } from "./tool-call-card";

export function formatClock(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
}

interface Props {
  run: RunInfo;
  agentName: string;
  expanded?: boolean;
  onOpenConversation?: (conversationId: string) => void;
}

/** One run as a card: who, what, status, cost, then the step timeline when expanded. */
export function RunCard({ run, agentName, expanded = false, onOpenConversation }: Props) {
  const [open, setOpen] = useState(expanded);
  const live = run.status === "running" || run.status === "awaiting_approval";
  return (
    <article className={`run-card ${run.status}`} data-testid="run-card" data-status={run.status}>
      <button type="button" className="run-summary" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className={`status-dot ${run.status}`} aria-hidden="true" />
        <span className="run-main">
          <span className="run-title">
            <strong>{agentName}</strong> · {run.title || vi.runSource(run.source)}
          </span>
          <span className="run-meta muted">
            {vi.runStatus[run.status]} · {formatClock(run.started_at)} · {vi.runSteps(run.steps.length)} ·{" "}
            {formatUsd(run.spent_usd)}
            {run.unknown_cost_calls > 0 && ` · ? ${run.unknown_cost_calls}`}
            {live && <span className="badge live"> {vi.liveNow}</span>}
          </span>
          {run.summary && <span className="run-preview muted">{run.summary}</span>}
        </span>
      </button>
      {open && (
        <div className="run-body">
          {run.steps.length === 0 ? (
            <p className="muted">{vi.thinking}</p>
          ) : (
            <ol className="run-steps">
              {run.steps.map((step, i) => (
                <StepRow key={i} step={step} />
              ))}
            </ol>
          )}
          {run.conversation_id && onOpenConversation && (
            <button
              type="button"
              className="link-button"
              onClick={() => onOpenConversation(run.conversation_id as string)}
            >
              {vi.openConversation}
            </button>
          )}
        </div>
      )}
    </article>
  );
}

function StepRow({ step }: { step: RunStep }) {
  const [showOutput, setShowOutput] = useState(false);
  const duration = step.duration_ms !== null ? vi.stepDuration(step.duration_ms) : null;
  if (step.kind === "model") {
    return (
      <li className="step model" data-testid="run-step">
        <span className="step-kind">🧠 {vi.stepModel}</span>
        <span className="step-detail">
          {step.model ?? "?"} · {vi.stepChars(step.chars)} ·{" "}
          {step.cost_usd === null ? vi.stepCostUnknown : formatUsd(step.cost_usd)}
          {duration && ` · ${duration}`}
          {step.tool_calls.length > 0 && ` · → ${step.tool_calls.join(", ")}`}
        </span>
        {step.preview && <span className="step-preview muted">{step.preview}</span>}
      </li>
    );
  }
  if (step.kind === "fallback") {
    return (
      <li className="step fallback" data-testid="run-step">
        <span className="step-kind">↪ {vi.stepFallback}</span>
        <span className="step-detail">
          {step.provider}:{step.model} · {step.error}
        </span>
      </li>
    );
  }
  const state = step.ok === null ? "running" : step.ok ? "done" : "failed";
  return (
    <li className={`step tool ${state}`} data-testid="run-step">
      <span className="step-kind">🔧 {step.name}</span>
      <span className={`tool-status ${state}`}>
        {state === "running" ? vi.toolRunning : state === "done" ? vi.toolDone : vi.toolFailed}
        {duration && ` · ${duration}`}
      </span>
      <span className="tool-arguments">{summarizeArguments(step.arguments) || "—"}</span>
      {step.output && (
        <>
          <button type="button" className="link-button" onClick={() => setShowOutput((s) => !s)}>
            {showOutput ? vi.hideOutput : vi.showOutput}
          </button>
          {showOutput && <pre className="tool-output">{step.output}</pre>}
        </>
      )}
    </li>
  );
}
