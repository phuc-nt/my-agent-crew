import type { PendingApproval } from "../state/thread-reducer";

/** A tool call waiting to be authorised, with only the fields a test cares about spelled
 *  out. Shared so that adding a field to the shape does not mean editing every test. */
export function toolPending(over: Partial<PendingApproval> = {}): PendingApproval {
  return {
    approvalId: "ap",
    toolCallId: "tc",
    name: "write_file",
    arguments: {},
    kind: "tool",
    options: [],
    ...over,
  };
}

/** A question waiting for a person's reply. */
export function questionPending(over: Partial<PendingApproval> = {}): PendingApproval {
  return toolPending({
    name: "ask_user",
    kind: "question",
    arguments: { question: "Dời hạn sang thứ sáu?" },
    ...over,
  });
}
