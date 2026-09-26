import { describe, expect, it } from "vitest";
import { fakeRun } from "../test/fake-backend";
import { runOutcome } from "./run-chip";

describe("runOutcome", () => {
  it("says how the run ended in a plain sentence, then what the run itself said", () => {
    expect(runOutcome(fakeRun({ status: "done", summary: "Đề xuất 2 trang." }))).toBe("Đã chạy xong. Đề xuất 2 trang.");
    expect(runOutcome(fakeRun({ status: "halted", summary: "" }))).toBe("Đã dừng giữa chừng.");
    expect(runOutcome(fakeRun({ status: "error", summary: "Hết hạn mức." }))).toBe("Chạy lỗi. Hết hạn mức.");
  });
});
