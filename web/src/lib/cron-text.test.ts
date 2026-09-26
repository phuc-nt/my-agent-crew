import { describe, expect, it } from "vitest";
import { cronText, everyText, scheduleText } from "./cron-text";

describe("a schedule's timing in words", () => {
  it.each([
    ["0 7 * * *", "Mỗi ngày 07:00"],
    ["30 21 * * *", "Mỗi ngày 21:30"],
    ["0 8,20 * * *", "Mỗi ngày 08:00, 20:00"],
    ["0 7 * * 0-6", "Mỗi ngày 07:00"],
    ["0 9 * * 1-5", "Thứ Hai–Thứ Sáu 09:00"],
    ["0 9 * * 1,2,3,4,5", "Thứ Hai–Thứ Sáu 09:00"],
    ["0 10 * * 0,6", "Cuối tuần 10:00"],
    ["0 10 * * 6,7", "Cuối tuần 10:00"],
    ["0 18 * * 5", "Thứ Sáu hằng tuần 18:00"],
    // Sunday written either way, and read last as a week is.
    ["0 20 * * 7", "Chủ Nhật hằng tuần 20:00"],
    ["0 20 * * 0,1", "Thứ Hai, Chủ Nhật hằng tuần 20:00"],
    ["0 * * * *", "Mỗi giờ"],
    ["15 * * * *", "Mỗi giờ vào phút 15"],
    ["0 */2 * * *", "Mỗi 2 giờ"],
    ["5 */6 * * *", "Mỗi 6 giờ vào phút 5"],
    ["* * * * *", "Mỗi phút"],
    ["*/15 * * * *", "Mỗi 15 phút"],
    ["0 3 1 * *", "Ngày 1 hằng tháng 03:00"],
    ["  0 7 * * *  ", "Mỗi ngày 07:00"],
  ])("reads %s as %s", (cron, words) => {
    expect(cronText(cron)).toBe(words);
  });

  // Every shape below is valid to the scheduler, but a sentence for it would either be
  // long or leave something out; the cron itself is the honest answer.
  it.each([
    "0 7 * 1 *",
    "0 7 1 * 1",
    "0 7-9 * * *",
    "*/10 9 * * *",
    "0 */5,7 * * *",
    "0 7 * * 5-1",
    "0 7 * * 8",
    "61 7 * * *",
    "0 24 * * *",
    "0 7 32 * *",
    "*/0 * * * *",
    // A step that does not divide the hour or the day restarts at :00 or at midnight, so
    // the last gap is shorter: "every 7 minutes" would be wrong once an hour.
    "*/7 * * * *",
    "*/45 * * * *",
    "0 */5 * * *",
    "0 */7 * * *",
    "0 7 * *",
    "@daily",
    "",
  ])("leaves %j as written", (cron) => {
    expect(cronText(cron)).toBe(cron);
  });

  it("reads the every shorthand in the units the scheduler accepts", () => {
    expect(everyText("30m")).toBe("Mỗi 30 phút");
    expect(everyText("1h")).toBe("Mỗi giờ");
    expect(everyText("2 d")).toBe("Mỗi 2 ngày");
    expect(everyText("90s")).toBe("Mỗi 90 giây");
    expect(everyText("1w")).toBe("1w");
  });

  it("uses whichever key the schedule is written with", () => {
    expect(scheduleText("0 7 * * *", null)).toBe("Mỗi ngày 07:00");
    expect(scheduleText(null, "30m")).toBe("Mỗi 30 phút");
    expect(scheduleText(null, null)).toBe("");
  });
});
