import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import { FakeBackend, fakeRun } from "../test/fake-backend";
import { RunReplay } from "./run-replay";

describe("RunReplay", () => {
  let backend: FakeBackend;

  beforeEach(() => {
    backend = new FakeBackend();
    vitest.stubGlobal("fetch", backend.fetch);
  });

  const show = (runId: string, known = [] as ReturnType<typeof fakeRun>[]) =>
    render(
      <RunReplay
        runId={runId}
        known={known}
        agentName={() => "Trợ lý"}
        onBack={() => undefined}
        onOpenConversation={() => undefined}
      />,
    );

  it("fetches a run the list never loaded, and shows its steps", async () => {
    // The point of the page: the activity list reaches back only so far, so a link to an
    // older run has to work without it being on screen already.
    backend.runs = [
      fakeRun({
        id: "old",
        title: "Dọn kho",
        steps: [
          { kind: "tool", name: "read_file", tool_call_id: "t1", arguments: { path: "a.md" }, ok: true, output: "xong", duration_ms: 12 },
        ],
      }),
    ];

    show("old");

    expect(await screen.findByTestId("run-card")).toHaveTextContent("Dọn kho");
    expect(screen.getByText(/read_file/)).toBeInTheDocument();
  });

  it("shows the arguments as names and values, not one row per character", async () => {
    // A run read back from the server is the only path that carries stored arguments;
    // flattened to a string they used to render as `0={, 1=', 2=p…`.
    backend.runs = [
      fakeRun({
        id: "old",
        steps: [
          { kind: "tool", name: "read_file", tool_call_id: "t1", arguments: { path: "notes.md" }, ok: true, output: "", duration_ms: 1 },
        ],
      }),
    ];

    show("old");

    expect(await screen.findByText("path=notes.md")).toBeInTheDocument();
  });

  it("prefers the copy already on screen, so a run still working keeps ticking", async () => {
    const fetched = vitest.fn(backend.fetch);
    vitest.stubGlobal("fetch", fetched);
    const live = fakeRun({ id: "live", status: "running", finished_at: null, title: "Đang làm" });

    show("live", [live]);

    expect(await screen.findByTestId("run-card")).toHaveTextContent("Đang làm");
    // Re-reading it would only race the stream that is already updating this object.
    expect(fetched).not.toHaveBeenCalled();
  });

  it("says so when the run is not there any more", async () => {
    show("missing");

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(vi.replay.notFound("missing")),
    );
    expect(screen.queryByTestId("run-card")).not.toBeInTheDocument();
  });

  it("offers a way back to the whole list", async () => {
    const onBack = vitest.fn();
    render(
      <RunReplay
        runId="missing"
        known={[]}
        agentName={() => "Trợ lý"}
        onBack={onBack}
        onOpenConversation={() => undefined}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: vi.replay.back }));
    expect(onBack).toHaveBeenCalled();
  });
});
