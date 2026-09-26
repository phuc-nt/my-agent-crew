import { describe, expect, it } from "vitest";
import { dayGroup, dayOffset, timeAgo, timeUntil } from "./relative-time";

// The suite runs in Asia/Ho_Chi_Minh (vite.config.ts), so 17:30Z is 00:30 on the 27th.
const now = new Date("2026-09-26T17:30:00Z");

describe("relative time on the viewer's calendar", () => {
  it("puts 23:00 local in yesterday although it shares the UTC date with now", () => {
    expect(new Date().getTimezoneOffset()).toBe(-420);
    expect(dayOffset("2026-09-26T16:00:00Z", now)).toBe(-1);
    expect(dayGroup("2026-09-26T16:00:00Z", now)).toBe("yesterday");
    expect(dayGroup("2026-09-26T17:10:00Z", now)).toBe("today");
    expect(dayGroup("2026-09-25T16:59:00Z", now)).toBe("older");
  });

  it("reads a clock-skewed future timestamp and a broken one without throwing", () => {
    expect(dayGroup("2026-09-26T18:00:00Z", now)).toBe("today");
    expect(dayGroup("not a date", now)).toBe("older");
    expect(timeAgo("not a date", now)).toBe("not a date");
  });

  it("says how long ago in the shortest words that still order a list", () => {
    expect(timeAgo("2026-09-26T17:29:30Z", now)).toBe("vừa xong");
    expect(timeAgo("2026-09-26T17:25:00Z", now)).toBe("5 phút");
    // Past midnight locally, so an hour and a half ago is already yesterday.
    expect(timeAgo("2026-09-26T16:00:00Z", now)).toBe("Hôm qua");
    expect(timeAgo("2026-09-24T03:00:00Z", now)).toBe("24/09");
    const noon = new Date("2026-09-27T05:00:00Z");
    expect(timeAgo("2026-09-27T02:00:00Z", noon)).toBe("3 giờ");
  });

  it("says how long until something scheduled", () => {
    expect(timeUntil("2026-09-26T17:30:20Z", now)).toBe("sắp tới");
    expect(timeUntil("2026-09-26T17:42:00Z", now)).toBe("sau 12 phút");
    expect(timeUntil("2026-09-27T00:00:00Z", now)).toBe("sau 6 giờ");
    expect(timeUntil("2026-09-28T00:00:00Z", now)).toBe("28/09 07:00");
  });
});
