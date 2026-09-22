import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import { emptyThread } from "../state/thread-reducer";
import { ErrorBoundary } from "./error-boundary";
import { splitMedia } from "./message-thread";
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
});

describe("splitMedia", () => {
  it("separates MEDIA: lines from text and keeps ordinary lines together", () => {
    expect(splitMedia("Đây là ảnh:\nMEDIA: out/chart.png\nxong")).toEqual([
      { kind: "text", value: "Đây là ảnh:" },
      { kind: "media", value: "out/chart.png" },
      { kind: "text", value: "xong" },
    ]);
    expect(splitMedia("MEDIA:")).toEqual([{ kind: "text", value: "MEDIA:" }]);
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
