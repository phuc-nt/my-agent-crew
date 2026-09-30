import { render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { describe, expect, it, vi as vitest } from "vitest";
import type { ContentHit } from "../api/types";
import { vi } from "../i18n/vi";
import { ContentHits } from "./content-hits";

const NOW = new Date("2026-09-30T05:00:00Z");
const agentName = (id: string) => (id === "coach" ? "Huấn luyện viên" : id);

function hit(overrides: Partial<ContentHit> = {}): ContentHit {
  return {
    conversation_id: "c1",
    agent_id: "coach",
    title: "Kế hoạch tuần",
    message_id: "m1",
    role: "user",
    snippet: "…đọc sách mỗi tối…",
    created_at: "2026-09-30T03:00:00Z",
    ...overrides,
  };
}

function hits(props: Partial<ComponentProps<typeof ContentHits>> = {}) {
  return (
    <ContentHits
      hits={null}
      loading={false}
      error={false}
      onRetry={() => {}}
      onSelect={() => {}}
      agentName={agentName}
      now={NOW}
      {...props}
    />
  );
}

describe("the 'Trong nội dung' content-hit list", () => {
  it("shows a loading state while the search is in flight", () => {
    render(hits({ loading: true }));
    expect(screen.getByText(vi.contentSearch.loading)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows an error state, distinct from an empty result, with a retry button", async () => {
    const user = userEvent.setup();
    const onRetry = vitest.fn();
    render(hits({ error: true, onRetry }));
    expect(screen.getByText(vi.contentSearch.error)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: vi.retry }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows nothing at all once settled with no hits, not an error", () => {
    const { container } = render(hits({ hits: [] }));
    expect(container).toBeEmptyDOMElement();
  });

  it("names each row's agent with a badge, and gives the button an accessible name naming the conversation", () => {
    render(
      hits({
        hits: [hit(), hit({ conversation_id: "c2", agent_id: "default", title: "Ghi chú" })],
      }),
    );
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(2);
    expect(buttons[0]).toHaveAccessibleName(expect.stringContaining("Kế hoạch tuần"));
    expect(buttons[1]).toHaveAccessibleName(expect.stringContaining("Ghi chú"));
    // The badge reads the looked-up display name, not the raw agent_id.
    expect(screen.getByText("Huấn luyện viên")).toBeInTheDocument();
    expect(screen.getByText("default")).toBeInTheDocument();
  });

  it("shows when each hit happened, relative to now", () => {
    render(hits({ hits: [hit()] }));
    expect(screen.getByRole("time")).toHaveAttribute("dateTime", "2026-09-30T03:00:00Z");
  });

  it("calls onSelect with the hit's conversation_id, not its message_id, when clicked", async () => {
    const user = userEvent.setup();
    const onSelect = vitest.fn();
    render(hits({ hits: [hit()], onSelect }));

    await user.click(screen.getByRole("button"));

    expect(onSelect).toHaveBeenCalledWith("c1");
    expect(onSelect).toHaveBeenCalledTimes(1);
  });
});
