import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi as vitest } from "vitest";
import type { RunInfo } from "../api/types";
import { useAttention } from "../hooks/use-attention-badge";
import { vi } from "../i18n/vi";
import { foldRepeats } from "../lib/attention-repeats";
import { fakeRun } from "../test/fake-backend";
import { AttentionCenter } from "./attention-center";

const name = () => "Agent";
const BACKUP = "job:health-coach/backup-to-drive";
const at = (day: number) => new Date(2026, 10, day, 2, 20).toISOString();

function Listed({ runs }: { runs: RunInfo[] }) {
  return <AttentionCenter runs={useAttention(runs)} agentName={name} onOpenConversation={() => undefined} />;
}

// A nightly job that failed three nights running listed three identical "02:20" rows.
const nights = (prefix: string) => [
  fakeRun({ id: `${prefix}-8`, source: BACKUP, status: "error", started_at: at(8) }),
  fakeRun({ id: `${prefix}-7`, source: BACKUP, status: "error", started_at: at(7) }),
  fakeRun({ id: `${prefix}-6`, source: BACKUP, status: "error", started_at: at(6) }),
];

describe("foldRepeats", () => {
  it("folds failures of one job into the newest and keeps everything else apart", () => {
    const chat = [fakeRun({ id: "c1", source: "web", status: "error" }), fakeRun({ id: "c2", source: "web", status: "error" })];
    const asks = [
      fakeRun({ id: "a1", source: BACKUP, status: "awaiting_approval", finished_at: null }),
      fakeRun({ id: "a2", source: BACKUP, status: "awaiting_approval", finished_at: null }),
    ];
    const halted = fakeRun({ id: "h1", source: BACKUP, status: "halted", started_at: at(5) });
    const rows = foldRepeats([...nights("f"), ...chat, ...asks, halted]);

    expect(rows.map((row) => [row.run.id, row.earlier.map((r) => r.id)])).toEqual([
      ["f-8", ["f-7", "f-6"]],
      ["c1", []],
      ["c2", []],
      ["a1", []],
      ["a2", []],
      ["h1", []],
    ]);
  });

  it("keeps the newest run as the row whatever order the runs came in", () => {
    const [newest, middle, oldest] = nights("o");
    const [row] = foldRepeats([middle, newest, oldest]);
    expect(row.run.id).toBe(newest.id);
    expect(row.earlier.map((r) => r.id).sort()).toEqual([middle.id, oldest.id].sort());
  });
});

describe("AttentionCenter repeated failures", () => {
  it("lists a job that failed night after night once, with how many times and the day", () => {
    render(<Listed runs={nights("r")} />);

    expect(screen.getAllByText(vi.attentionFailed("Agent"))).toHaveLength(1);
    expect(screen.getByText(`· ${vi.attentionRepeats(3)}`, { exact: false })).toBeInTheDocument();
  });

  it("says a run of another day by its date, not by a clock that reads as today's", () => {
    vitest.useFakeTimers({ now: new Date(2026, 10, 8, 9, 0), toFake: ["Date"] });
    render(<Listed runs={[fakeRun({ id: "old-day", source: BACKUP, status: "error", started_at: at(2) })]} />);

    vitest.useRealTimers();
    const when = screen.getByText("02/11");
    expect(when.tagName).toBe("TIME");
    expect(when).toHaveAttribute("title", "02/11 02:20");
  });

  it("reads every folded failure once the row is marked as read", async () => {
    const { unmount } = render(<Listed runs={nights("s")} />);

    await userEvent.click(screen.getByRole("button", { name: vi.attentionSeenLabel(vi.attentionFailed("Agent")) }));
    expect(screen.getByText(vi.attentionEmpty)).toBeInTheDocument();
    unmount();

    // Listed again, as after a reload: none of the three comes back.
    render(<Listed runs={nights("s")} />);
    expect(screen.queryByText(vi.attentionFailed("Agent"))).not.toBeInTheDocument();
  });
});

describe("AttentionCenter memory proposals", () => {
  it("points to the memory rewrites waiting instead of saying nothing needs you", async () => {
    const onOpenProposals = vitest.fn();
    render(<AttentionCenter runs={[]} agentName={name} onOpenConversation={() => undefined} inline proposalsElsewhere={2} onOpenProposals={onOpenProposals} />);

    expect(screen.queryByText(vi.attentionEmpty)).not.toBeInTheDocument();
    expect(screen.getByTestId("attention")).not.toHaveClass("calm");
    await userEvent.click(screen.getByRole("button", { name: vi.attentionProposals(2) }));
    expect(onOpenProposals).toHaveBeenCalled();
  });
});
