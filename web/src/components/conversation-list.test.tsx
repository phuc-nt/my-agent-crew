import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { Conversation, RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { memoryStorage, refusingStorage } from "../test/memory-storage";
import { ConversationList } from "./conversation-list";

// The suite runs in Asia/Ho_Chi_Minh (vite.config.ts): this is noon on the 26th there.
const NOW = "2026-09-26T05:00:00Z";

function conversation(id: string, updated_at: string, overrides: Partial<Conversation> = {}): Conversation {
  return {
    id,
    agent_id: "default",
    title: id,
    status: "idle",
    channel: "",
    created_at: "2026-09-20T01:00:00Z",
    updated_at,
    autonomous: false,
    cost_cap_usd: 1,
    spent_usd: 0,
    unknown_cost_calls: 0,
    over_budget: false,
    summary: "",
    skills: [],
    auto_approve: [],
    parent_call_id: "",
    ...overrides,
  };
}

type LiveRun = Pick<RunInfo, "conversation_id" | "status">;

function list(conversations: Conversation[], activeId: string | null, liveRuns?: LiveRun[]) {
  return (
    <ConversationList
      conversations={conversations}
      activeId={activeId}
      liveRuns={liveRuns}
      onSelect={() => {}}
      onCreate={() => {}}
      onDelete={() => {}}
    />
  );
}

const row = (title: string) => screen.getByText(title, { selector: ".conversation-title" }).closest("li")!;
const dots = () => screen.queryAllByTestId("unread-dot").map((d) => d.closest("li")!.querySelector(".conversation-title")!.textContent);

beforeEach(() => {
  vitest.useFakeTimers({ toFake: ["Date"] });
  vitest.setSystemTime(new Date(NOW));
  memoryStorage();
});

afterEach(() => {
  vitest.useRealTimers();
  vitest.unstubAllGlobals();
});

describe("the sidebar's day groups", () => {
  it("files rows under the viewer's own day, not the UTC date, each with how long ago", () => {
    render(
      list(
        [
          conversation("Sáng nay", "2026-09-26T03:00:00Z"),
          // 00:30 on the 26th in Hanoi, although the UTC date is still the 25th.
          conversation("Nửa đêm", "2026-09-25T17:30:00Z"),
          // 01:00 on the 25th in Hanoi: yesterday, while its UTC date is the 24th.
          conversation("Rạng sáng qua", "2026-09-24T18:00:00Z"),
          conversation("Tối hôm kia", "2026-09-24T16:30:00Z"),
        ],
        null,
      ),
    );

    const groups = screen.getAllByRole("region");
    expect(groups.map((g) => within(g).getByRole("heading").textContent)).toEqual([
      vi.time.groups.today,
      vi.time.groups.yesterday,
      vi.time.groups.older,
    ]);
    const titles = (g: HTMLElement) =>
      Array.from(g.querySelectorAll(".conversation-title"), (t) => t.textContent);
    expect(titles(groups[0])).toEqual(["Sáng nay", "Nửa đêm"]);
    expect(titles(groups[1])).toEqual(["Rạng sáng qua"]);
    expect(titles(groups[2])).toEqual(["Tối hôm kia"]);

    expect(within(row("Sáng nay")).getByText("2 giờ")).toHaveAttribute("dateTime", "2026-09-26T03:00:00Z");
    expect(within(row("Rạng sáng qua")).getByText("Hôm qua")).toBeInTheDocument();
    expect(within(row("Tối hôm kia")).getByText("24/09")).toBeInTheDocument();
  });

  it("shows no header for a day with nothing in it", () => {
    render(list([conversation("Cũ", "2026-09-01T03:00:00Z")], null));
    expect(screen.getAllByRole("heading").map((h) => h.textContent)).toEqual([vi.time.groups.older]);
  });
});

describe("the unread dot", () => {
  const a = (updated = "2026-09-26T04:00:00Z") => conversation("a", updated);
  const b = (updated = "2026-09-26T03:00:00Z") => conversation("b", updated);

  it("marks a reply that lands elsewhere, clears on opening, and comes back on the next one", () => {
    const view = render(list([a(), b()], "a"));
    // Everything before the first visit counts as read.
    expect(dots()).toEqual([]);

    view.rerender(list([b("2026-09-26T05:01:00Z"), a()], "a"));
    expect(dots()).toEqual(["b"]);
    expect(row("b")).toHaveClass("unread");
    expect(within(row("b")).getByText(vi.unread)).toBeInTheDocument();

    view.rerender(list([b("2026-09-26T05:01:00Z"), a()], "b"));
    expect(dots()).toEqual([]);

    // Leaving it with nothing new keeps it read.
    view.rerender(list([b("2026-09-26T05:01:00Z"), a()], "a"));
    expect(dots()).toEqual([]);

    view.rerender(list([b("2026-09-26T05:02:00Z"), a()], "a"));
    expect(dots()).toEqual(["b"]);
  });

  it("never marks the open conversation or one an agent delegated", () => {
    const view = render(list([a(), b()], "a"));
    const child = conversation("con", "2026-09-26T05:03:00Z", { parent_call_id: "tc-1" });
    view.rerender(list([a("2026-09-26T05:02:00Z"), child, b()], "a"));
    expect(dots()).toEqual([]);
  });

  it("remembers what was seen across a reload", () => {
    const first = render(list([a(), b()], "b"));
    first.rerender(list([b("2026-09-26T05:01:00Z"), a()], "b"));
    first.unmount();

    render(list([b("2026-09-26T05:01:00Z"), a()], "a"));
    expect(dots()).toEqual([]);
  });

  it("still lists everything, just without memory, where storage is refused", () => {
    refusingStorage();
    const view = render(list([a(), b()], "a"));
    view.rerender(list([b("2026-09-26T05:01:00Z"), a()], "a"));
    expect(dots()).toEqual(["b"]);
    view.rerender(list([b("2026-09-26T05:01:00Z"), a()], "b"));
    expect(dots()).toEqual([]);
  });
});

describe("the status dot", () => {
  const dot = (title: string) => row(title).querySelector(".status-dot")!;

  it("names every state in Vietnamese, idle included, and pulses while a run is live", () => {
    render(
      list(
        [
          conversation("rảnh", "2026-09-26T04:00:00Z"),
          conversation("chờ", "2026-09-26T03:00:00Z", { status: "awaiting_approval" }),
          conversation("chạy", "2026-09-26T02:00:00Z"),
        ],
        null,
        [{ conversation_id: "chạy", status: "running" }],
      ),
    );
    expect(dot("rảnh")).toHaveAttribute("title", "Rảnh");
    expect(dot("chờ")).toHaveAttribute("title", "Chờ bạn duyệt");
    expect(dot("chạy")).toHaveAttribute("title", "Đang chạy");
    expect(dot("chạy")).toHaveClass("running");
  });

  // While an approval is pending its run is live too; the row must still say that it is
  // the owner's turn, not the agent's.
  it("says a live run waiting for approval is waiting, even where the row is a turn behind", () => {
    render(
      list(
        [
          conversation("chờ", "2026-09-26T04:00:00Z", { status: "awaiting_approval" }),
          // Fetched before the tool asked: the row still reads idle.
          conversation("vừa hỏi", "2026-09-26T03:00:00Z"),
          conversation("hai lượt", "2026-09-26T02:00:00Z"),
        ],
        null,
        [
          { conversation_id: "chờ", status: "awaiting_approval" },
          { conversation_id: "vừa hỏi", status: "awaiting_approval" },
          { conversation_id: "hai lượt", status: "awaiting_approval" },
          { conversation_id: "hai lượt", status: "running" },
        ],
      ),
    );
    for (const title of ["chờ", "vừa hỏi", "hai lượt"]) {
      expect(dot(title)).toHaveAttribute("title", "Chờ bạn duyệt");
      expect(dot(title)).toHaveClass("awaiting_approval");
      expect(dot(title)).not.toHaveClass("running");
    }
  });
});
