import { describe, expect, it } from "vitest";
import { clashingIds, idsToSend } from "./schedule-ids";

const rows = (...ids: string[]) => ids.map((id) => ({ id }));

describe("the id each schedule row is saved under", () => {
  it("leaves a blank id blank while the server's own numbering is free", () => {
    expect(idsToSend(rows("", "brief", ""))).toEqual(["", "brief", ""]);
  });

  it("fills a blank id that would land on a kept row's", () => {
    expect(idsToSend(rows("job-1", ""))).toEqual(["job-1", "job-2"]);
  });

  // The second blank row's own place, job-2, went to the first one: it moves on as well.
  it("never hands two blank rows the same id", () => {
    expect(idsToSend(rows("job-1", "", ""))).toEqual(["job-1", "job-2", "job-3"]);
    expect(new Set(idsToSend(rows("job-2", "job-1", "", "")))).toHaveProperty("size", 4);
  });

  it("never renames a typed id", () => {
    expect(idsToSend(rows("job-1", "job-1"))).toEqual(["job-1", "job-1"]);
  });
});

describe("a typed id the server would refuse", () => {
  it("is the second of two equal ids", () => {
    expect([...clashingIds(rows("a", "b", "a", ""), false)]).toEqual([[2, "taken"]]);
  });

  it("is the consolidation job's id only while consolidation is on", () => {
    expect([...clashingIds(rows("memory-consolidate"), true)]).toEqual([[0, "reserved"]]);
    expect(clashingIds(rows("memory-consolidate"), false).size).toBe(0);
  });
});
