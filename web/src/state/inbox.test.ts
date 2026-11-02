import { describe, expect, it } from "vitest";
import { fakeRun } from "../test/fake-backend";
import { jobName, jobResults, mergeRuns, unreadResults } from "./inbox";

const job = (id: string, finished: string, overrides = {}) =>
  fakeRun({ id, source: `job:${id}`, finished_at: finished, summary: `Báo cáo ${id}`, ...overrides });

describe("the jobs' results", () => {
  it("lists finished job runs with something to say, the latest to finish first", () => {
    const runs = [
      job("a", "2026-11-01T01:00:00Z"),
      fakeRun({ id: "chat", source: "web" }),
      job("b", "2026-11-01T03:00:00Z"),
      job("failed", "2026-11-01T04:00:00Z", { status: "error" }),
      job("running", "2026-11-01T05:00:00Z", { status: "running", finished_at: null }),
      job("quiet", "2026-11-01T06:00:00Z", { summary: "" }),
      // A command's output, not an answer: the chat is not sent it.
      job("command", "2026-11-01T07:00:00Z", { conversation_id: null }),
    ];
    expect(jobResults(runs).map((r) => r.id)).toEqual(["b", "a"]);
  });

  // A check job's "all is well" is not delivered to the chat, so the inbox does not list it.
  it("leaves out a reply that only says OK", () => {
    const runs = ["OK", "ok.", " OK! ", "OK, nhưng ổ đĩa sắp đầy"].map((summary, n) =>
      job(`j${n}`, `2026-11-01T0${n}:00:00Z`, { summary }),
    );
    expect(jobResults(runs).map((r) => r.summary)).toEqual(["OK, nhưng ổ đĩa sắp đầy"]);
  });

  it("counts as unread what finished after the inbox was read, and everything before it ever was", () => {
    const results = jobResults([job("a", "2026-11-01T01:00:00Z"), job("b", "2026-11-01T03:00:00+00:00")]);
    expect(unreadResults(results, null)).toHaveLength(2);
    expect(unreadResults(results, "2026-11-01T02:00:00.000Z").map((r) => r.id)).toEqual(["b"]);
    expect(unreadResults(results, "2026-11-01T03:00:00.000Z")).toEqual([]);
  });

  it("merges two lists by id, keeping the later list's copy", () => {
    const merged = mergeRuns([job("a", "2026-11-01T01:00:00Z"), job("b", "x")], [job("a", "2026-11-01T02:00:00Z")]);
    expect(merged.map((r) => [r.id, r.finished_at])).toEqual([
      ["a", "2026-11-01T02:00:00Z"],
      ["b", "x"],
    ]);
  });

  it("names the job without the schedule's mark or the time the card says", () => {
    expect(jobName("[lịch] Bản tin sáng · 2026-11-01 07:00")).toBe("Bản tin sáng");
    expect(jobName("[lịch] A · B · 2026-11-01 07:00")).toBe("A · B");
    expect(jobName("Bản tin")).toBe("Bản tin");
  });
});
