import { describe, expect, it } from "vitest";

import { vi } from "../i18n/vi";
import {
  type DelegateResult,
  delegateAgent,
  delegateReason,
  delegateTask,
  delegateTone,
  parseDelegateResult,
} from "./delegate-result";

const HEADER = "conversation=c-9 status=done spent=$0.0421 steps=7";
const PLAN = "3f9a1c2b7d40";
const SOURCES = "9b1e0c44a7d2";
const tag = (id: string, version: number, title: string) => `[artifact ${id} v${version}] ${title}`;

describe("parseDelegateResult", () => {
  it("splits the header from the child's reply", () => {
    const parsed = parseDelegateResult(`${HEADER}\nĐã sửa xong hai tệp.\nCòn một câu hỏi.`);

    expect(parsed).toEqual({
      conversationId: "c-9",
      status: "done",
      spentUsd: 0.0421,
      steps: 7,
      canvases: [],
      reply: "Đã sửa xong hai tệp.\nCòn một câu hỏi.",
    });
  });

  it("reads a header with no reply after it", () => {
    expect(parseDelegateResult(HEADER)?.reply).toBe("");
  });

  it("reads what the task came to, and why, from the second line", () => {
    const output = `${HEADER}\noutcome=blocked reason=workspace_write denied\nKhông ghi được.`;

    expect(parseDelegateResult(output)).toEqual({
      conversationId: "c-9",
      status: "done",
      spentUsd: 0.0421,
      steps: 7,
      outcome: "blocked",
      outcomeReason: "workspace_write denied",
      canvases: [],
      reply: "Không ghi được.",
    });
  });

  it("reads an outcome with no reason, and one with no reply after it", () => {
    const done = parseDelegateResult(`${HEADER}\noutcome=done\nĐã xong.`);
    const timedOut = parseDelegateResult(`${HEADER}\noutcome=failed reason=timeout`);

    expect(done?.outcome).toBe("done");
    expect(done).not.toHaveProperty("outcomeReason");
    expect(done?.reply).toBe("Đã xong.");
    expect(timedOut?.outcomeReason).toBe("timeout");
    expect(timedOut?.reply).toBe("");
  });

  it("leaves the outcome out for a result written before there was one", () => {
    // Older results in the history go straight from the header to the reply.
    const parsed = parseDelegateResult(`${HEADER}\nĐã sửa.\noutcome=done`);

    expect(parsed).not.toHaveProperty("outcome");
    expect(parsed?.reply).toBe("Đã sửa.\noutcome=done");
  });

  it("returns nothing when the output is an error instead of a result", () => {
    // The tool can fail before it opens a child; the card then shows the text as-is.
    expect(parseDelegateResult("Hết thời gian chờ agent con.")).toBeNull();
    expect(parseDelegateResult("")).toBeNull();
  });
});

describe("the canvases a delegate result names", () => {
  const read = (...lines: string[]) => parseDelegateResult([HEADER, ...lines].join("\n"));

  it("reads the lines under the outcome, up to the blank line, as what the child wrote", () => {
    const parsed = read(
      "outcome=done",
      tag(PLAN, 2, "Dàn ý pha cà phê phin"),
      tag(SOURCES, 10, "Nguồn [1] v2"),
      "",
      "Mình đã viết dàn ý 6 mục.",
      "",
      "Còn một câu hỏi.",
    );

    expect(parsed?.canvases).toEqual([
      { id: PLAN, version: 2, title: "Dàn ý pha cà phê phin" },
      { id: SOURCES, version: 10, title: "Nguồn [1] v2" },
    ]);
    expect(parsed?.reply).toBe("Mình đã viết dàn ý 6 mục.\n\nCòn một câu hỏi.");
    expect(parsed?.outcome).toBe("done");
  });

  it("reads a blank line right under the outcome as a child that wrote none", () => {
    const parsed = read("outcome=done", "", "Đã tra xong.", "", "Hết.");

    expect(parsed?.canvases).toEqual([]);
    expect(parsed?.reply).toBe("Đã tra xong.\n\nHết.");
  });

  it("reads a result stored before the blank line was there as the reply alone", () => {
    const paragraphs = read("outcome=done", "Đã sửa hai tệp.", "", "Còn một câu hỏi.");
    const oneLine = read("outcome=done", "Đã sửa hai tệp.");
    // A line of spaces is not the line the server writes: the tag above it is the child's text.
    const spaces = read("outcome=done", tag(PLAN, 1, "Dàn ý"), " ", "Hết.");
    // Older still: no outcome line, and what looks like a canvas block is the child's own text.
    const noOutcome = read(tag(PLAN, 1, "Dàn ý"), "", "Đã xong.");

    expect(paragraphs?.canvases).toEqual([]);
    expect(paragraphs?.reply).toBe("Đã sửa hai tệp.\n\nCòn một câu hỏi.");
    expect(oneLine?.canvases).toEqual([]);
    expect(oneLine?.reply).toBe("Đã sửa hai tệp.");
    expect(spaces?.canvases).toEqual([]);
    expect(spaces?.reply).toBe(`${tag(PLAN, 1, "Dàn ý")}\n \nHết.`);
    expect(noOutcome?.canvases).toEqual([]);
    expect(noOutcome?.reply).toBe(`${tag(PLAN, 1, "Dàn ý")}\n\nĐã xong.`);
  });

  it("leaves a reply that opens with a line like a canvas tag in the reply", () => {
    // The blank line the server always writes comes first, so the block above it is empty.
    const parsed = read("outcome=done", "", tag(PLAN, 3, "Canvas không có thật"), "Đã xong.");

    expect(parsed?.canvases).toEqual([]);
    expect(parsed?.reply).toBe(`${tag(PLAN, 3, "Canvas không có thật")}\nĐã xong.`);
  });

  it("does not read a line like a canvas tag further down as a canvas", () => {
    const below = read(
      "outcome=done",
      tag(PLAN, 1, "Dàn ý"),
      "",
      "Kết quả công cụ artifact_create:",
      tag(SOURCES, 1, "Nguồn"),
      "",
      "Hết.",
    );
    // An older result: the tag is not on the first lines alone, so none of them is a canvas.
    const mixed = read("outcome=done", "Đã viết:", tag(PLAN, 1, "Dàn ý"), "", "Hết.");
    const afterTag = read("outcome=done", tag(PLAN, 1, "Dàn ý"), "Đã viết xong.", "", "Hết.");

    expect(below?.canvases).toEqual([{ id: PLAN, version: 1, title: "Dàn ý" }]);
    expect(below?.reply).toBe(
      `Kết quả công cụ artifact_create:\n${tag(SOURCES, 1, "Nguồn")}\n\nHết.`,
    );
    expect(mixed?.canvases).toEqual([]);
    expect(mixed?.reply).toBe(`Đã viết:\n${tag(PLAN, 1, "Dàn ý")}\n\nHết.`);
    expect(afterTag?.canvases).toEqual([]);
    expect(afterTag?.reply).toBe(`${tag(PLAN, 1, "Dàn ý")}\nĐã viết xong.\n\nHết.`);
  });

  it("takes only the tag a write names a canvas with for a canvas line", () => {
    const lines = [
      `[artifact ${PLAN} v1 unchanged] Dàn ý`,
      `[artifact ${PLAN} v1]`,
      `[artifact ${PLAN.toUpperCase()} v1] Dàn ý`,
      `[artifact ${PLAN.slice(1)} v1] Dàn ý`,
      `[artifact ${PLAN}0 v1] Dàn ý`,
      `[artifact ${PLAN.replace("f", "g")} v1] Dàn ý`,
      `[artifact ${PLAN} v] Dàn ý`,
      `[artifact ${PLAN} vx] Dàn ý`,
      `[artifact ${PLAN} v1]Dàn ý`,
      ` ${tag(PLAN, 1, "Dàn ý")}`,
      `- ${tag(PLAN, 1, "Dàn ý")}`,
    ];

    for (const line of lines) {
      const parsed = read("outcome=done", line, "", "Hết.");

      expect(parsed?.canvases, line).toEqual([]);
      expect(parsed?.reply, line).toBe(`${line}\n\nHết.`.trim());
    }
  });

  it("reads a line that ends at the space after the tag as a canvas with no title", () => {
    // The store refuses an empty title; one that got through must not cost the whole block.
    const parsed = read("outcome=done", tag(PLAN, 1, "Dàn ý"), `[artifact ${SOURCES} v4] `, "", "Hết.");

    expect(parsed?.canvases).toEqual([
      { id: PLAN, version: 1, title: "Dàn ý" },
      { id: SOURCES, version: 4, title: "" },
    ]);
    expect(parsed?.reply).toBe("Hết.");
  });

  it("keeps the count of the canvases left out in the reply", () => {
    const ids = Array.from({ length: 12 }, (_, n) => (n + 1).toString(16).padStart(12, "0"));
    const more = "(+2 canvas khác, xem bằng artifact_list)";
    const parsed = read(
      "outcome=done",
      ...ids.map((id, n) => tag(id, 1, `Mục ${n + 1}`)),
      "",
      more,
      "",
      "Đã viết 14 canvas.",
    );

    expect(parsed?.canvases.map((canvas) => canvas.id)).toEqual(ids);
    expect(parsed?.canvases[11]).toEqual({ id: ids[11], version: 1, title: "Mục 12" });
    expect(parsed?.reply).toBe(`${more}\n\nĐã viết 14 canvas.`);
  });

  it("reads what a child had written when the wait for it ran out", () => {
    const waiting = "conversation=c-9 status=awaiting_approval spent=$0.0100 steps=2";
    const said = "Hết thời gian chờ agent con. Xem cuộc c-9 để biết nó đang ở đâu.";
    const parsed = parseDelegateResult(
      [waiting, "outcome=failed reason=timeout", tag(PLAN, 1, "Dàn ý"), "", said].join("\n"),
    );

    expect(parsed?.canvases).toEqual([{ id: PLAN, version: 1, title: "Dàn ý" }]);
    expect(parsed?.reply).toBe(said);
    expect(parsed && delegateReason(parsed)).toBe(vi.delegateTimeout);
  });
});

describe("delegateTone", () => {
  const base: DelegateResult = {
    conversationId: "c",
    status: "done",
    spentUsd: 0,
    steps: 1,
    canvases: [],
    reply: "",
  };

  it("goes by the outcome when there is one", () => {
    expect(delegateTone({ ...base, outcome: "done" })).toBe("ok");
    expect(delegateTone({ ...base, outcome: "blocked" })).toBe("warn");
    expect(delegateTone({ ...base, outcome: "done_with_concerns" })).toBe("warn");
    expect(delegateTone({ ...base, outcome: "failed" })).toBe("danger");
  });

  it("goes by how the run ended for a result that has no outcome", () => {
    expect(delegateTone(base)).toBe("ok");
    expect(delegateTone({ ...base, status: "halted" })).toBe("danger");
  });
});

describe("delegateReason", () => {
  const ended = (status: string, outcome: string, outcomeReason?: string): DelegateResult => ({
    conversationId: "c",
    status,
    spentUsd: 0,
    steps: 1,
    outcome,
    outcomeReason,
    canvases: [],
    reply: "",
  });

  it("says in words how the child's run stopped", () => {
    expect(delegateReason(ended("halted", "failed", "loop"))).toBe(vi.haltedLoop);
    expect(delegateReason(ended("halted", "failed", "budget"))).toBe(vi.haltedBudget);
    expect(delegateReason(ended("halted", "failed", "max_steps"))).toBe(vi.haltedMaxSteps);
    expect(delegateReason(ended("error", "failed", "interrupted"))).toBe(vi.runInterrupted);
    expect(delegateReason(ended("error", "failed", "error"))).toBe(vi.runEndedError);
    expect(delegateReason(ended("error", "failed", "Nhà cung cấp trả lỗi 500"))).toBe(
      "Nhà cung cấp trả lỗi 500",
    );
  });

  it("reads a wait that ran out only while the child was still going", () => {
    expect(delegateReason(ended("running", "failed", "timeout"))).toBe(vi.delegateTimeout);
    expect(delegateReason(ended("awaiting_approval", "failed", "timeout"))).toBe(
      vi.delegateTimeout,
    );
    // An error message that happens to be the word is the error, as written.
    expect(delegateReason(ended("error", "failed", "timeout"))).toBe("timeout");
  });

  it("names the tool whose approval was refused or lapsed", () => {
    expect(delegateReason(ended("done", "blocked", "workspace_write denied"))).toBe(
      vi.delegateRefused.denied("workspace_write"),
    );
    expect(delegateReason(ended("done", "blocked", "shell_run expired"))).toBe(
      vi.delegateRefused.expired("shell_run"),
    );
  });

  it("shows what the child wrote as it wrote it", () => {
    expect(delegateReason(ended("done", "blocked", "cần quyền tạo bảng"))).toBe(
      "cần quyền tạo bảng",
    );
    expect(delegateReason(ended("done", "needs_context", "thiếu ngày"))).toBe("thiếu ngày");
    // Only the runtime writes codes, and never for a task the child finished with concerns.
    expect(delegateReason(ended("done", "done_with_concerns", "loop"))).toBe("loop");
  });

  it("has nothing to say for a task that is done or a result from before outcomes", () => {
    expect(delegateReason(ended("done", "done"))).toBe("");
    expect(delegateReason({ ...ended("halted", "failed"), outcome: undefined })).toBe("");
  });
});

describe("delegateTask", () => {
  it("cuts a long task and leaves a short one alone", () => {
    expect(delegateTask({ task: "  dọn mã  " })).toBe("dọn mã");
    expect(delegateTask({ task: "x".repeat(200) })).toHaveLength(141);
    expect(delegateTask({ task: "x".repeat(200) }).endsWith("…")).toBe(true);
  });

  it("survives arguments that are not what we expect", () => {
    expect(delegateTask({})).toBe("");
    expect(delegateTask({ task: 7 })).toBe("");
    expect(delegateAgent({ agent: "coder" })).toBe("coder");
    expect(delegateAgent({})).toBe("");
  });
});
