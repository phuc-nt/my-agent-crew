import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { QueuedMessage } from "../api/types";
import { vi } from "../i18n/vi";
import { QueuedChips } from "./queued-chips";

const followUp: QueuedMessage = { id: 1, kind: "follow_up", text: "việc đầu tiên chờ sau lượt này" };
const steer: QueuedMessage = { id: 2, kind: "steer", text: "chen vao ngay bay gio" };

describe("the chips a queued message becomes", () => {
  it("renders nothing when there is nothing waiting", () => {
    const { container } = render(<QueuedChips items={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("carries the full text in the DOM even though the row itself is a single truncated line", () => {
    const long = "một câu khá dài để chắc chắn rằng chữ vẫn còn nguyên trong DOM dù dòng bị cắt".repeat(3);
    render(<QueuedChips items={[{ id: 3, kind: "follow_up", text: long }]} />);
    expect(screen.getByText(long)).toBeInTheDocument();
  });

  it("announces itself with aria-live so a chip appearing is read out without moving focus", () => {
    render(<QueuedChips items={[followUp]} />);
    const list = screen.getByRole("list", { name: vi.queuedLabel });
    expect(list).toHaveAttribute("aria-live", "polite");
  });

  it("labels a follow-up chip and a steer chip differently for someone using a screen reader", () => {
    render(<QueuedChips items={[followUp, steer]} />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent(vi.queuedFollowUp);
    expect(items[1]).toHaveTextContent(vi.queuedSteer);
  });

  it("offers no button: a chip is confirmation only, nothing here can be cancelled", () => {
    render(<QueuedChips items={[followUp, steer]} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
