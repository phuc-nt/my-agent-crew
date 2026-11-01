import { describe, expect, it } from "vitest";
import { fakeRun } from "../test/fake-backend";
import { waitingInDelegated } from "./delegated-requests";

const waits = (id: string, conversation: string, source: string) =>
  fakeRun({ id, conversation_id: conversation, source, status: "awaiting_approval", finished_at: null });
const runs = (id: string, conversation: string, source: string) =>
  fakeRun({ id, conversation_id: conversation, source, status: "running", finished_at: null });

const ids = (found: { id: string }[]) => found.map((r) => r.id);

describe("waitingInDelegated", () => {
  it("finds a child's request and leaves out the conversation's own and an unrelated one", () => {
    const own = waits("own", "root", "chat");
    const child = waits("child", "kid", "delegate:root");
    const stranger = waits("stranger", "other-kid", "delegate:other-root");
    const all = [own, child, stranger, runs("parent", "root", "chat")];
    expect(ids(waitingInDelegated(all, [own, child, stranger], "root"))).toEqual(["child"]);
  });

  // The middle child's own run is still going, waiting on the delegate call it made.
  it("reaches a grandchild through the child that delegated to it", () => {
    const grandchild = waits("grand", "kid2", "delegate:kid1");
    const all = [runs("middle", "kid1", "delegate:root"), grandchild];
    expect(ids(waitingInDelegated(all, [grandchild], "root"))).toEqual(["grand"]);
    expect(ids(waitingInDelegated(all, [grandchild], "kid1"))).toEqual(["grand"]);
    expect(waitingInDelegated(all, [grandchild], "kid2")).toEqual([]);
  });

  // A child decided once resumes under the deciding channel's name, and can pause again.
  it("links a child paused again after a decision through its first delegated run", () => {
    const again = waits("again", "kid", "chat");
    const first = fakeRun({ id: "first", conversation_id: "kid", source: "delegate:root" });
    expect(ids(waitingInDelegated([again, first], [again], "root"))).toEqual(["again"]);
  });

  it("ignores runs that are no longer waiting and stops on a loop in the links", () => {
    const loopA = runs("a", "x", "delegate:y");
    const loopB = waits("b", "y", "delegate:x");
    const settled = fakeRun({ id: "done", conversation_id: "kid", source: "delegate:root" });
    expect(waitingInDelegated([loopA, loopB, settled], [loopB, settled], "root")).toEqual([]);
  });
});
