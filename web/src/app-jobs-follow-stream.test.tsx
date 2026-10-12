// A job's row is read when its run ends. The server counts that run into the job's streak
// of failures after that, and tells the owner after that again, a wait of up to a minute.
// So the row a page read at the run's end said no notice had got through, of one that
// arrived a moment later, and went on saying so until some other run ended. The streak
// now says while a notice is on its way, and the stream says when the list changed after
// a run was over, on which the page reads it again.
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { JobFailing, JobInfo } from "./api/types";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, FakeEventSource, coachAgent, fakeAgent, fakeRun } from "./test/fake-backend";

const t = vi.jobRow;
const TOLD = "Đã báo Telegram lúc";
const failed = fakeRun({ id: "r-err", agent_id: "coach", conversation_id: null, source: "job:coach/brief", status: "error" });
const briefJob: JobInfo = {
  ...coachAgent.schedules[0], id: "coach/brief", schedule_id: "brief", agent_id: "coach",
  next_run: null, last_run: null, running: false, paused: false, origin: "profile",
};
const streak = { count: 1, since: failed.started_at, told_at: null, next_notice_at: null, telling: false };
const telling: JobFailing = { ...streak, telling: true };
const told: JobFailing = { ...streak, told_at: "2026-09-19T08:00:06Z", next_notice_at: "2026-09-19T14:00:06Z" };
/** The row as the server gives it once the run has ended in an error. */
const failing = (state: JobFailing): JobInfo[] => [{ ...briefJob, last_run: failed, failing: state }];

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  backend.agents = [fakeAgent, coachAgent];
  FakeEventSource.instances = [];
  vitest.stubGlobal("fetch", backend.fetch);
  vitest.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vitest.unstubAllGlobals();
  window.location.hash = "";
});

const stream = () => FakeEventSource.instances.at(-1)!;
const jobReads = () => backend.requests.filter((r) => r.method === "GET" && r.path === "/jobs").length;
const sentence = () => screen.getByTestId("job-failing").textContent ?? "";

/** Opens the jobs list on what the server holds now. */
async function opensJobs(jobs: JobInfo[]) {
  backend.jobs = jobs;
  window.location.hash = "#/manage/jobs";
  render(<App />);
  await waitFor(() => expect(screen.getAllByTestId("job")).toHaveLength(1));
  expect(jobReads()).toBe(1);
}

/** Each read of the job list is answered with what the server held when it was asked. The
 *  reads named in `hold` reach the page only once released, so an answer read while a notice
 *  was on its way can land after one read once it had arrived; those in `lose` never do. */
function network({ hold = [], lose = [] }: { hold?: number[]; lose?: number[] }) {
  const releases = new Map<number, () => void>();
  let reads = 0;
  let handed = 0;
  vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input) !== "/api/jobs") return backend.fetch(input, init);
    const n = ++reads;
    const response = await backend.fetch(input, init);
    if (lose.includes(n)) throw new TypeError("Failed to fetch");
    if (hold.includes(n)) await new Promise<void>((resolve) => releases.set(n, resolve));
    handed += 1;
    return response;
  });
  return { release: (n: number) => releases.get(n)?.(), handed: () => handed };
}

describe("the jobs list, while the owner is being told that a job failed", () => {
  it("reads the row again when the stream says the list changed, with no run ending", async () => {
    await opensJobs(failing(telling));
    expect(sentence()).toContain(t.streakTelling);

    backend.jobs = failing(told);
    act(() => stream().emit({ type: "jobs" }));

    await waitFor(() => expect(sentence()).toContain(TOLD));
    expect(sentence()).not.toContain(t.streakTelling);
    expect(jobReads()).toBe(2);
  });

  it("says a notice did not get through once the stream says so", async () => {
    await opensJobs(failing(telling));

    backend.jobs = failing(streak);
    act(() => stream().emit({ type: "jobs" }));

    await waitFor(() => expect(sentence()).toContain(t.streakUntold));
    expect(sentence()).not.toContain(t.streakTelling);
  });

  it("no longer says a job is failing once the stream says it mended", async () => {
    await opensJobs(failing(told));

    backend.jobs = [{ ...briefJob, last_run: fakeRun({ id: "r-ok", agent_id: "coach", source: "job:coach/brief" }) }];
    act(() => stream().emit({ type: "jobs" }));

    await waitFor(() => expect(screen.queryByTestId("job-failing")).not.toBeInTheDocument());
    expect(screen.getAllByTestId("job")).toHaveLength(1);
  });

  // The two reads are out at once: one asked for at the run's end, one when the stream said
  // the owner had been told. Whichever lands last used to be the one shown.
  it("keeps what it read last when the read from the run's end answers after it", async () => {
    const net = network({ hold: [2] });
    await opensJobs([briefJob]);

    // The run ends and the page asks for the list. The server answers with the notice
    // still on its way, and that answer is kept from the page for now.
    backend.jobs = failing(telling);
    act(() => stream().emit({ type: "run", run: failed }));
    await waitFor(() => expect(jobReads()).toBe(2));

    backend.jobs = failing(told);
    act(() => stream().emit({ type: "jobs" }));
    await waitFor(() => expect(sentence()).toContain(TOLD));
    expect(net.handed()).toBe(2);

    await act(async () => {
      net.release(2);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(net.handed()).toBe(3);
    expect(sentence()).toContain(TOLD);
    expect(sentence()).not.toContain(t.streakTelling);
  });

  // As before the stream said anything: a list that could not be read is not shown as the
  // one read earlier, which may be out of date by now.
  it("says the list could not be read when the read the stream asked for fails", async () => {
    network({ lose: [2] });
    await opensJobs(failing(telling));

    act(() => stream().emit({ type: "jobs" }));

    expect(await screen.findByText(vi.loadFailed)).toBeInTheDocument();
    expect(screen.queryByTestId("job")).not.toBeInTheDocument();
  });
});
