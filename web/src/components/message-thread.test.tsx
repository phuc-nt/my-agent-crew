import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RunInfo, RunStep } from "../api/types";
import { vi } from "../i18n/vi";
import type { ThreadItem } from "../state/thread-reducer";
import { fakeRun } from "../test/fake-backend";
import { MessageThread } from "./message-thread";

const userItem: ThreadItem = { id: "m1", kind: "user", text: "tìm sách đi" };

function waiting(liveRun: RunInfo | null) {
  return render(
    <MessageThread
      items={[userItem]}
      streaming={null}
      busy
      liveRun={liveRun}
      onSuggestion={() => {}}
      echoOnly={false}
      agentId="master"
    />,
  );
}

const openTool: RunStep = {
  kind: "tool",
  name: "web_search",
  tool_call_id: "t1",
  arguments: {},
  ok: null,
  output: null,
  duration_ms: null,
};

describe("MessageThread while the agent is working", () => {
  it("names the tool the turn is blocked on instead of only saying it is thinking", () => {
    // The whole point of putting the header here: a reader who never opens the
    // rail still learns what the wait is for.
    waiting(fakeRun({ status: "running", steps: [openTool] }));
    expect(screen.getByTestId("thinking")).toHaveTextContent(vi.runDoing("web_search"));
  });

  it("counts the steps and the clock, so a long wait reads as progress not a hang", () => {
    waiting(
      fakeRun({
        status: "running",
        steps: [{ ...openTool, tool_call_id: "t0", ok: true, duration_ms: 20 }, openTool],
      }),
    );
    expect(screen.getByTestId("thinking")).toHaveTextContent(vi.runStepCount(1, 2));
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("says the plain word when no run has arrived yet", () => {
    // The gap between sending and the first activity event: there is nothing
    // truthful to show beyond the fact that something was sent.
    waiting(null);
    expect(screen.getByTestId("thinking")).toHaveTextContent(vi.thinking);
    expect(screen.queryByRole("progressbar")).toBeNull();
  });
});

describe("who gets their text formatted", () => {
  function thread(items: ThreadItem[]) {
    return render(
      <MessageThread
        items={items}
        streaming={null}
        busy={false}
        onSuggestion={() => {}}
        echoOnly={false}
        agentId="master"
      />,
    );
  }

  it("formats the agent's reply", () => {
    const { container } = thread([
      { id: "a1", kind: "assistant", text: "**ngủ đủ** giúp hồi phục", model: null },
    ]);
    expect(container.querySelector("strong")?.textContent).toBe("ngủ đủ");
  });

  it("leaves what the person typed exactly as they typed it", () => {
    // Someone who writes an asterisk means an asterisk; their message is not a
    // document the app gets to reinterpret.
    const { container } = thread([{ id: "m2", kind: "user", text: "**giữ nguyên** nhé" }]);
    expect(container.querySelector("strong")).toBeNull();
    expect(screen.getByTestId("message-user").textContent).toContain("**giữ nguyên**");
  });

  it("keeps images inline when a reply mixes prose and a MEDIA line", () => {
    const { container } = thread([
      { id: "a2", kind: "assistant", text: "**Biểu đồ**\nMEDIA: out/chart.png\nXong.", model: null },
    ]);
    expect(container.querySelector("strong")?.textContent).toBe("Biểu đồ");
    expect(container.querySelector("img.media")?.getAttribute("src")).toContain(
      encodeURIComponent("out/chart.png"),
    );
  });
});
