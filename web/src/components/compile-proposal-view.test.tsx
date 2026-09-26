import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { MemoryProposal } from "../api/types";
import { vi } from "../i18n/vi";
import { CompileProposalView } from "./compile-proposal-view";

const page = (slug: string, title: string, body: string, extra: object = {}) => ({
  slug,
  kind: "entities",
  title,
  body,
  sources: ["2026-09-20"],
  questions: [],
  status: "ok",
  ...extra,
});

function proposal(body: unknown, previous: unknown): MemoryProposal {
  return {
    id: "p1",
    agent_id: "default",
    kind: "wiki_compile",
    name: "wiki",
    description: "2 trang",
    type: "",
    body: typeof body === "string" ? body : JSON.stringify(body),
    previous_body: JSON.stringify(previous),
    status: "pending",
    source: "memory:wiki",
    created_at: "2026-09-20T07:00:00",
    resolved_at: null,
  };
}

describe("CompileProposalView", () => {
  it("renders one card per page, tagged new or updated from what existed before", async () => {
    const pages = [
      page("han-eco", "Hạn Eco", "Hạn 30/9.\nCòn thiếu ảnh.", { questions: ["Ai chụp?"] }),
      page("da-lat", "Đà Lạt", "Chuyến đi tháng 10.", { kind: "syntheses", status: "review" }),
    ];
    render(<CompileProposalView proposal={proposal(pages, [page("han-eco", "Hạn Eco", "Hạn 25/9.\nCòn thiếu ảnh.")])} />);

    const cards = within(screen.getByRole("list", { name: vi.memory.compilePages(2) })).getAllByRole("listitem");
    expect(cards).toHaveLength(2);
    expect(within(cards[0]).getByText(vi.memory.compileUpdated)).toBeInTheDocument();
    expect(within(cards[0]).getByText("Hạn Eco")).toBeInTheDocument();
    expect(cards[0]).toHaveTextContent(vi.memory.compileQuestions(1));
    expect(within(cards[1]).getByText(vi.memory.compileNew)).toBeInTheDocument();
    expect(cards[1]).toHaveTextContent(vi.wiki.kinds.syntheses);
    expect(within(cards[1]).getByText(vi.wiki.needsReview)).toBeInTheDocument();

    // An updated page opens onto exactly what changes; a new page onto its body.
    await userEvent.click(within(cards[0]).getByText(vi.memory.compileShowChanges));
    expect(within(cards[0]).getByText("- Hạn 25/9.")).toHaveClass("removed");
    expect(within(cards[0]).getByText("+ Hạn 30/9.")).toHaveClass("added");
    await userEvent.click(within(cards[1]).getByText(vi.memory.compileShowBody));
    expect(within(cards[1]).getByText("Chuyến đi tháng 10.")).toBeInTheDocument();
  });

  it("falls back to the raw text when the stored batch is not JSON", () => {
    render(<CompileProposalView proposal={proposal("không phải json", [])} />);
    expect(screen.getByText("không phải json")).toBeInTheDocument();
    expect(screen.queryByRole("listitem")).toBeNull();
  });
});
