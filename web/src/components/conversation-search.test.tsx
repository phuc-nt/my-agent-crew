import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi as vitest } from "vitest";
import type { Conversation } from "../api/types";
import { vi } from "../i18n/vi";
import { ConversationList } from "./conversation-list";
import { fold, matching } from "./conversation-search";

function conversation(id: string, title: string, summary = ""): Conversation {
  return {
    id,
    agent_id: "default",
    channel: "",
    title,
    summary,
    created_at: "",
    updated_at: "",
    autonomous: false,
    cost_cap_usd: 1,
    skills: [],
    auto_approve: [],
    spent_usd: 0,
    unknown_cost_calls: 0,
    status: "idle",
    over_budget: false,
    messages: [],
    pending_approval: null,
  } as unknown as Conversation;
}

describe("fold", () => {
  it("strips accents so a query typed without them still matches", () => {
    expect(fold("Tìm Sách")).toBe("tim sach");
  });

  it("turns đ into d, which decomposition on its own never does", () => {
    // `đ` is its own letter rather than a d with a mark, so NFD leaves it whole and
    // "doc" would never reach "đọc" without replacing it first.
    expect(fold("đọc")).toBe("doc");
    expect(matching([conversation("c1", "Đọc sách")], "doc")).toHaveLength(1);
  });
});

describe("matching", () => {
  const list = [
    conversation("c1", "Tìm sách hay", "gợi ý vài cuốn"),
    conversation("c2", "Dọn kho ảnh"),
  ];

  it("reads the summary as well as the title", () => {
    expect(matching(list, "gợi ý").map((c) => c.id)).toEqual(["c1"]);
  });

  it("an empty query hides nothing", () => {
    expect(matching(list, "   ")).toHaveLength(2);
  });

  it("no match is an empty list rather than everything", () => {
    expect(matching(list, "hoá đơn")).toEqual([]);
  });
});

describe("ConversationList search box", () => {
  const many = Array.from({ length: 9 }, (_, i) => conversation(`c${i}`, `Cuộc ${i}`));

  function list(conversations: Conversation[]) {
    return render(
      <ConversationList
        conversations={conversations}
        activeId={null}
        onSelect={vitest.fn()}
        onCreate={vitest.fn()}
        onDelete={vitest.fn()}
      />,
    );
  }

  it("stays out of the way until the list is long enough to need it", () => {
    list(many.slice(0, 3));
    expect(screen.queryByLabelText(vi.searchConversations)).not.toBeInTheDocument();
  });

  it("filters the list as the query is typed and says when nothing is left", async () => {
    list([...many, conversation("found", "Đọc sách buổi tối")]);

    await userEvent.type(screen.getByLabelText(vi.searchConversations), "doc sach");
    expect(screen.getAllByRole("button", { name: /Đọc sách buổi tối/ })).toHaveLength(1);
    expect(screen.queryByText("Cuộc 1")).not.toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(vi.searchConversations), " không có");
    expect(screen.getByTestId("no-matches")).toHaveTextContent(vi.noMatchingConversations);
  });
});
