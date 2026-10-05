import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import { emptyThread } from "../state/thread-reducer";
import { ErrorBoundary } from "./error-boundary";
import { StatusLine } from "./status-line";

describe("StatusLine", () => {
  it("reports thread state and stream connection for assistive tech", () => {
    const { rerender } = render(<StatusLine thread={emptyThread} connected liveCount={2} />);
    const line = screen.getByRole("status");
    expect(line).toHaveTextContent(vi.statusIdle);
    expect(line).toHaveTextContent(`${vi.liveNow}: 2`);
    rerender(
      <StatusLine
        thread={{ ...emptyThread, busy: true, items: [{ kind: "tool", id: "t", name: "shell_run", arguments: {}, output: null, status: "running" }] }}
        connected={false}
        liveCount={0}
      />,
    );
    expect(line).toHaveTextContent(vi.statusTool("shell_run"));
    expect(line).toHaveTextContent(vi.streamDisconnected);
  });

  it("says the agent is thinking over an earlier progress note", () => {
    const thread = { ...emptyThread, busy: true, thinking: true, items: [{ kind: "note" as const, id: "n", text: "Đang đọc dữ liệu" }] };
    render(<StatusLine thread={thread} connected liveCount={0} />);
    expect(screen.getByRole("status")).toHaveTextContent(vi.statusThinking);
  });

  it("names the stream's four states in one case, as they take turns in one slot", () => {
    for (const text of [vi.streamConnected, vi.streamConnecting, vi.streamDisconnected, vi.streamOffline]) {
      expect(text[0]).toBe(text[0].toLocaleUpperCase("vi"));
    }
  });

  it("says a spent budget locks the thread over an earlier note, until a turn runs", () => {
    const thread = { ...emptyThread, items: [{ kind: "note" as const, id: "n", text: "Đang đọc dữ liệu" }] };
    const { rerender } = render(<StatusLine thread={thread} connected liveCount={0} overBudget />);
    const line = screen.getByRole("status");
    expect(line).toHaveTextContent(vi.statusOverBudget);
    expect(line).not.toHaveTextContent("Đang đọc dữ liệu");
    rerender(<StatusLine thread={{ ...thread, busy: true, thinking: true }} connected liveCount={0} overBudget />);
    expect(line).toHaveTextContent(vi.statusThinking);
  });
});

describe("ErrorBoundary", () => {
  it("shows the failure and a reload button instead of a blank page", () => {
    const Boom = () => {
      throw new Error("vỡ");
    };
    vitest.spyOn(console, "error").mockImplementation(() => undefined);
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(vi.crashed);
    expect(screen.getByRole("alert")).toHaveTextContent("vỡ");
    expect(screen.getByRole("button", { name: vi.reload })).toBeInTheDocument();
  });
});
