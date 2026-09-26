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

  let runId = "";

  // Split from `show` so a test can hand over a later frame of the same run — which is
  // what the stream does — without rebuilding the component around it.
  const replay = (known: ReturnType<typeof fakeRun>[]) => (
    <RunReplay
      runId={runId}
      known={known}
      agentName={() => "Trợ lý"}
      onBack={() => undefined}
      onOpenConversation={() => undefined}
    />
  );

  const show = (id: string, known = [] as ReturnType<typeof fakeRun>[]) => {
    runId = id;
    return render(replay(known));
  };

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

  it("shows a tool result that arrived without its call, instead of breaking the page", async () => {
    // A turn resumed after an approval gets the result while the call was written on the
    // run that paused, so the server opens the step with no arguments and no call id.
    backend.runs = [
      fakeRun({
        id: "resumed",
        steps: [{ kind: "tool", name: "workspace_write", ok: false, output: "Bị từ chối", duration_ms: 0 }],
      }),
    ];

    show("resumed");

    const step = await screen.findByTestId("run-step");
    expect(step).toHaveTextContent("workspace_write");
    expect(step).toHaveTextContent("—");
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

  // The stream's last word about a run carries its final status but not its finish
  // time, and a settled run is never refreshed from the list again — so the copy in
  // memory keeps a finish time that never arrives, and only the fetch has the real one.
  it("re-reads a run that has settled, whose copy on screen can be missing its finish time", async () => {
    const settled = fakeRun({ id: "r1", status: "done", finished_at: null, title: "Đang làm" });
    backend.runs = [fakeRun({ id: "r1", status: "done", title: "Đã xong" })];

    show("r1", [settled]);

    expect(await screen.findByTestId("run-card")).toHaveTextContent("Đã xong");
  });

  // The ordinary way a run settles is while someone is watching it, and the stream hands
  // over a new object for the same run on every frame. The re-read has to happen once, on
  // the one frame the status changes — not on each of the frames before or after it.
  it("re-reads a run once when it settles under the eye, not on every frame", async () => {
    const fetched = vitest.fn(backend.fetch);
    vitest.stubGlobal("fetch", fetched);
    backend.runs = [fakeRun({ id: "r1", status: "done", title: "Đã xong" })];
    const frame = (status: "running" | "done") =>
      fakeRun({ id: "r1", status, finished_at: null, title: "Đang làm" });

    const view = show("r1", [frame("running")]);
    // Two more frames of the same unsettled run: a new object each time, no new fetch.
    view.rerender(replay([frame("running")]));
    view.rerender(replay([frame("running")]));
    expect(fetched).not.toHaveBeenCalled();

    view.rerender(replay([frame("done")]));
    expect(await screen.findByTestId("run-card")).toHaveTextContent("Đã xong");

    // And it stays at one: the stream goes on handing over frames of the settled run.
    view.rerender(replay([frame("done")]));
    view.rerender(replay([frame("done")]));
    await waitFor(() => expect(fetched).toHaveBeenCalledTimes(1));
  });

  // The fetch is only after a better copy of something already on screen. Reporting a
  // failure over a run the person can plainly see would be worse than showing it.
  it("keeps showing the run it already has when re-reading it fails", async () => {
    const settled = fakeRun({ id: "gone", status: "done", title: "Vẫn đây" });

    show("gone", [settled]);

    await waitFor(() => expect(screen.getByTestId("run-card")).toHaveTextContent("Vẫn đây"));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
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
