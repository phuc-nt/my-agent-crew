import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { RunStep } from "../api/types";
import { vi } from "../i18n/vi";
import { FAILED_KEPT_CHARS } from "../lib/step-preview";
import type { ThreadItem } from "../state/thread-reducer";
import { fakeRun } from "../test/fake-backend";
import { RunCard } from "./run-timeline";
import { ToolCallCard } from "./tool-call-card";

const ADVICE = "Hãy gọi workspace_write trực tiếp để chủ duyệt.";
/** As long as a failed step is ever kept at, ending with what to do instead. */
const REASON = `${"Lời gọi bị từ chối. ".repeat(40)}`.slice(0, FAILED_KEPT_CHARS - ADVICE.length) + ADVICE;

type ToolStep = Extract<RunStep, { kind: "tool" }>;
type ToolItem = Extract<ThreadItem, { kind: "tool" }>;

const step = (overrides: Partial<ToolStep> = {}): ToolStep => ({
  kind: "tool", name: "workspace_write", tool_call_id: "tc", arguments: { path: "a.md" }, ok: false, output: REASON, duration_ms: 20, ...overrides,
});

const card = (overrides: Partial<ToolItem> = {}): ToolItem => ({
  kind: "tool", id: "tc", name: "workspace_write", arguments: { path: "a.md" }, output: REASON, status: "failed", ...overrides,
});

const row = (steps: RunStep[]) => <RunCard run={fakeRun({ steps })} agentName="HLV" expanded />;
const box = (within_: HTMLElement) => within_.querySelector(".tool-output");

describe("what a failed step of a run handed back", () => {
  it("is on the row without a press, whole, in a box that does not scroll", () => {
    expect(REASON).toHaveLength(FAILED_KEPT_CHARS);
    render(row([step()]));
    const [failed] = screen.getAllByTestId("run-step");

    expect(failed).toHaveAttribute("data-state", "failed");
    expect(box(failed)).toHaveTextContent(REASON, { normalizeWhitespace: false });
    expect(box(failed)).toHaveClass("whole");
  });

  it("folds when asked and opens again", async () => {
    render(row([step()]));
    const [failed] = screen.getAllByTestId("run-step");

    await userEvent.click(within(failed).getByRole("button", { name: vi.hideOutput }));
    expect(box(failed)).toBeNull();
    await userEvent.click(within(failed).getByRole("button", { name: vi.showOutput }));
    expect(box(failed)).toHaveTextContent(ADVICE);
  });

  // A step heard live is on the row before it ends; how it ended decides, not how it began.
  it("opens when a step that was running ends in failure", () => {
    const running = fakeRun({ status: "running", finished_at: null, steps: [step({ ok: null, output: null, duration_ms: null })] });
    const view = render(<RunCard run={running} agentName="HLV" expanded />);
    expect(box(screen.getByTestId("run-step"))).toBeNull();

    view.rerender(<RunCard run={{ ...running, steps: [step()] }} agentName="HLV" expanded />);

    expect(box(screen.getByTestId("run-step"))).toHaveTextContent(ADVICE);
  });

  it("stays folded for a step that went through, in the box that scrolls", async () => {
    render(row([step({ ok: true, output: "đã ghi a.md" })]));
    const [done] = screen.getAllByTestId("run-step");

    expect(box(done)).toBeNull();
    await userEvent.click(within(done).getByRole("button", { name: vi.showOutput }));
    expect(box(done)).toHaveTextContent("đã ghi a.md");
    expect(box(done)).not.toHaveClass("whole");
  });

  it("is whole on a call a script made, once the script's calls are opened", () => {
    const call = { name: "workspace_write", arguments: { path: "a.md" }, ok: false, output: REASON, ms: 4, cost_usd: null, metered: false };
    render(row([step({ name: "tool_script", ok: true, output: "xong", calls: [call] })]));

    expect(screen.getByTestId("script-call-output").textContent).toBe(REASON);
  });
});

describe("what a failed call handed back, on its card in the chat", () => {
  it.each(["failed", "denied"] as const)("is on a %s card without a press, whole", (status) => {
    render(<ToolCallCard item={card({ status })} />);
    const shown = box(screen.getByTestId("tool-card"));

    expect(shown).toHaveTextContent(REASON, { normalizeWhitespace: false });
    expect(shown).toHaveClass("whole");
    expect(screen.getByRole("button", { name: vi.hideOutput })).toBeInTheDocument();
  });

  // The card holds everything the tool handed back, which for a command that failed may be
  // pages: open, and all of it there, but in the box that scrolls.
  it("is open in the box that scrolls when it is longer than a step keeps", () => {
    const pages = `${"dòng lỗi\n".repeat(400)}${ADVICE}`;
    render(<ToolCallCard item={card({ name: "shell_run", output: pages })} />);
    const shown = box(screen.getByTestId("tool-card"));

    expect(shown?.textContent).toBe(pages);
    expect(shown).not.toHaveClass("whole");
  });

  it("is the reply of a task handed off that failed, without a press", () => {
    const output = `conversation=c-child status=running spent=$0.0250 steps=4\noutcome=failed reason=timeout\n${ADVICE}`;
    render(<ToolCallCard item={card({ name: "delegate", arguments: { agent_id: "coach", task: "Dọn" }, output })} />);
    const shown = box(screen.getByTestId("delegate-card"));

    expect(shown?.textContent).toBe(ADVICE);
    expect(shown).toHaveClass("whole");
  });

  it("stays folded on a card that went through", () => {
    render(<ToolCallCard item={card({ status: "done", output: "đã ghi a.md" })} />);

    expect(box(screen.getByTestId("tool-card"))).toBeNull();
    expect(screen.getByRole("button", { name: vi.showOutput })).toBeInTheDocument();
  });
});
