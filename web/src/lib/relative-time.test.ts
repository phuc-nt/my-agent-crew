import { describe, expect, it } from "vitest";
import { calendarDate, dayClock, dayGroup, dayOffset, timeAgo, timeUntil } from "./relative-time";

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

describe("a time as a sentence names it", () => {
  // Built from local clock fields, not from an instant in UTC: the reading is about the
  // viewer's own day, and it has to hold in whatever zone the suite runs.
  const local = (day: number, hour: number, minute: number) => new Date(2026, 8, day, hour, minute);
  const iso = (day: number, hour: number, minute: number) => local(day, hour, minute).toISOString();
  const midMorning = local(27, 9, 30);

  it("writes the clock alone for today, earlier or later than now", () => {
    expect(dayClock(iso(27, 0, 5), midMorning)).toBe("00:05");
    expect(dayClock(iso(27, 9, 30), midMorning)).toBe("09:30");
    expect(dayClock(iso(27, 23, 59), midMorning)).toBe("23:59");
  });

  it("names yesterday from its first minute to its last", () => {
    expect(dayClock(iso(26, 0, 0), midMorning)).toBe("Hôm qua 00:00");
    expect(dayClock(iso(26, 23, 59), midMorning)).toBe("Hôm qua 23:59");
    // Half an hour after midnight, a time 90 minutes back is already yesterday's.
    expect(dayClock(iso(26, 23, 0), local(27, 0, 30))).toBe("Hôm qua 23:00");
  });

  it("writes the date with the clock for any other day, tomorrow included", () => {
    expect(dayClock(iso(25, 23, 59), midMorning)).toBe("25/09 23:59");
    expect(dayClock(iso(1, 7, 5), midMorning)).toBe("01/09 07:05");
    expect(dayClock(iso(28, 0, 0), midMorning)).toBe("28/09 00:00");
  });

  it("hands back a timestamp it cannot read", () => {
    expect(dayClock("not a date", midMorning)).toBe("not a date");
  });
});

describe("a day with its year", () => {
  it("is the viewer's own day, month and year, each day and month as two digits", () => {
    expect(calendarDate(new Date(2026, 10, 12, 9, 30).toISOString())).toBe("12/11/2026");
    expect(calendarDate(new Date(2027, 0, 3, 23, 59).toISOString())).toBe("03/01/2027");
  });

  it("is the day the viewer lives in, where the instant falls on another day in UTC", () => {
    expect(new Date().getTimezoneOffset()).toBe(-420);
    // 17:30 UTC on the 11th is half past midnight on the 12th in Hanoi.
    expect(calendarDate("2026-11-11T17:30:00+00:00")).toBe("12/11/2026");
    expect(calendarDate("2026-12-31T17:00:00+00:00")).toBe("01/01/2027");
  });

  it("hands back a timestamp it cannot read", () => {
    expect(calendarDate("not a date")).toBe("not a date");
  });
});
