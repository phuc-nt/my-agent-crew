import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import type { RunInfo } from "../api/types";
import { useAttention } from "../hooks/use-attention-badge";
import { vi } from "../i18n/vi";
import { fakeRun } from "../test/fake-backend";
import { AttentionCenter } from "./attention-center";

const name = () => "Agent";

afterEach(() => vitest.unstubAllGlobals());

/** The list as the app shows it: failures marked as read are filtered out by the hook. */
function Listed({ runs }: { runs: RunInfo[] }) {
  const shown = useAttention(runs);
  return <AttentionCenter runs={shown} agentName={name} onOpenConversation={() => undefined} />;
}

// The seen list is one per page, so each case dismisses runs no other case lists.
describe("AttentionCenter failures", () => {
  it("hides a failure once it is marked as read and keeps the others", async () => {
    render(<Listed runs={[fakeRun({ id: "seen-err", status: "error" }), fakeRun({ id: "seen-halt", status: "halted" })]} />);

    await userEvent.click(screen.getByRole("button", { name: vi.attentionSeenLabel(vi.attentionFailed("Agent")) }));

    expect(screen.queryByText(vi.attentionFailed("Agent"))).not.toBeInTheDocument();
    expect(screen.getByText(vi.attentionHalted("Agent"))).toBeInTheDocument();
  });

  it("still hides a failure when the browser refuses storage", async () => {
    const refuse = () => {
      throw new DOMException("denied", "SecurityError");
    };
    vitest.stubGlobal("localStorage", { getItem: refuse, setItem: refuse, clear: refuse });
    render(<Listed runs={[fakeRun({ id: "no-storage", status: "error" })]} />);

    await userEvent.click(screen.getByRole("button", { name: vi.attentionSeenLabel(vi.attentionFailed("Agent")) }));

    expect(screen.queryByText(vi.attentionFailed("Agent"))).not.toBeInTheDocument();
    expect(screen.getByText(vi.attentionEmpty)).toBeInTheDocument();
  });

  // A request waiting on a decision has a deadline; "read" would let it expire unseen.
  it("offers no way to dismiss a request that waits on a decision", () => {
    render(<Listed runs={[fakeRun({ id: "asks", status: "awaiting_approval", finished_at: null })]} />);

    expect(screen.getByText(vi.attentionAwaiting("Agent"))).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: new RegExp(vi.attentionSeen) })).not.toBeInTheDocument();
  });

  it("points to the requests waiting in another section instead of saying nothing waits", async () => {
    const onOpenWaiting = vitest.fn();
    render(<AttentionCenter runs={[]} agentName={name} onOpenConversation={() => undefined} waitingElsewhere={2} onOpenWaiting={onOpenWaiting} />);

    expect(screen.queryByText(vi.attentionEmpty)).not.toBeInTheDocument();
    expect(screen.getByTestId("attention")).not.toHaveClass("calm");
    await userEvent.click(screen.getByRole("button", { name: vi.attentionWaitingElsewhere(2) }));
    expect(onOpenWaiting).toHaveBeenCalled();
  });

  // Duyệt lists only requests; the nav still counts unread failures on Hoạt động.
  it("points to the failures listed in another section instead of saying nothing needs you", async () => {
    const onOpenFailed = vitest.fn();
    render(<AttentionCenter runs={[]} agentName={name} onOpenConversation={() => undefined} inline failedElsewhere={3} onOpenFailed={onOpenFailed} />);

    expect(screen.queryByText(vi.attentionEmpty)).not.toBeInTheDocument();
    expect(screen.getByTestId("attention")).not.toHaveClass("calm");
    await userEvent.click(screen.getByRole("button", { name: vi.attentionFailedElsewhere(3) }));
    expect(onOpenFailed).toHaveBeenCalled();
  });
});
