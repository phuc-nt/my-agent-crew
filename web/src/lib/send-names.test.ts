import { describe, expect, it } from "vitest";
import { sendNames, type SendNames } from "./send-names";

const HEX = /^[0-9a-f]{32}$/;
const run = (id: string, conversation: string | null = "c1") => ({ id, conversation_id: conversation });

/** A send to c1 that nothing was heard of, and the name it went out under. */
function unheard(names: SendNames, text = "tiếp tục", reading = false): string {
  const sent = names.take("c1", text, reading);
  names.keep("c1", text, sent);
  return sent.name;
}

/** The name the same words would go out to c1 under now. Asking spends a kept name. */
const again = (names: SendNames, text = "tiếp tục") => names.take("c1", text, false).name;

describe("the name a message is sent under", () => {
  it("is a new one for each send", () => {
    const names = sendNames();
    const first = names.take("c1", "chào", false).name;
    expect(first).toMatch(HEX);
    expect(names.take("c1", "chào", false).name).not.toBe(first);
  });

  it("is kept for the same words to the same conversation after a send nothing was heard of", () => {
    const names = sendNames();
    const first = unheard(names);
    expect(again(names)).toBe(first);
    // Sent again and not kept a second time: the words are a new message from here on.
    expect(again(names)).not.toBe(first);
  });

  it("is not kept for other words, and the old name does not come back after them", () => {
    const names = sendNames();
    const first = unheard(names);
    expect(again(names, "tiếp tục nhé")).not.toBe(first);
    expect(again(names)).not.toBe(first);
  });

  it("is not kept for another conversation", () => {
    const names = sendNames();
    const first = unheard(names);
    expect(names.take("c2", "tiếp tục", false).name).not.toBe(first);
  });
});

describe("the name of a send nothing was heard of, as runs come and go in its conversation", () => {
  it("is kept while the turn that began after it is still going", () => {
    const names = sendNames();
    const first = unheard(names);
    names.going([run("r1")]);
    expect(again(names)).toBe(first);
  });

  it("is dropped once a turn that began after it is seen to end", () => {
    const names = sendNames();
    const first = unheard(names);
    names.going([run("r1")]);
    names.going([]);
    expect(again(names)).not.toBe(first);
  });

  it("is kept through a pause: the run is still there, waiting on the person", () => {
    const names = sendNames();
    const first = unheard(names);
    names.going([run("r1")]);
    names.going([run("r1")]);
    expect(again(names)).toBe(first);
  });

  it("is kept when the turn that ends was going already as the name went out: the message waits behind it", () => {
    const names = sendNames();
    names.going([run("r0")]);
    const first = unheard(names);
    names.going([]);
    expect(again(names)).toBe(first);
  });

  it("is dropped by the end of the turn that follows the one it waited behind", () => {
    const names = sendNames();
    names.going([run("r0")]);
    const first = unheard(names);
    names.going([]);
    names.going([run("r1")]);
    names.going([]);
    expect(again(names)).not.toBe(first);
  });

  it("is kept when the turn it waited behind gives way to its own, still going", () => {
    const names = sendNames();
    names.going([run("r0")]);
    const first = unheard(names);
    names.going([run("r1")]);
    expect(again(names)).toBe(first);
  });

  it("is kept when a turn came and went before the send was known to have failed", () => {
    // Nothing of that turn was shown as the message's own: sent again, it is answered with
    // what became of it.
    const names = sendNames();
    const sent = names.take("c1", "tiếp tục", false);
    names.going([run("r1")]);
    names.going([]);
    names.keep("c1", "tiếp tục", sent);
    names.going([]);
    expect(again(names)).toBe(sent.name);
  });

  it("is dropped by a turn found going when the send failed, once that turn is over", () => {
    const names = sendNames();
    const sent = names.take("c1", "tiếp tục", false);
    names.going([run("r1")]);
    names.keep("c1", "tiếp tục", sent);
    names.going([]);
    expect(again(names)).not.toBe(sent.name);
  });

  it("is kept whatever runs come and go in other conversations, or in none", () => {
    const names = sendNames();
    const first = unheard(names);
    names.going([run("r8", "c2"), run("r9", null)]);
    names.going([]);
    expect(again(names)).toBe(first);
  });

  it("is told apart from the turn the tab was reading only when that turn's run was known", () => {
    const names = sendNames();
    // Reading a turn no run was known for: the next run to end may be that one.
    const blind = unheard(names, "việc hai", true);
    names.going([run("r1")]);
    names.going([]);
    expect(again(names, "việc hai")).toBe(blind);

    names.going([run("r2")]);
    const told = unheard(names, "việc ba", true);
    names.going([]);
    names.going([run("r3")]);
    names.going([]);
    expect(again(names, "việc ba")).not.toBe(told);
  });

  it("is not told apart from the turn the tab was reading by a run known in another conversation", () => {
    const names = sendNames();
    names.going([run("r8", "c2")]);
    const blind = unheard(names, "việc hai", true);
    names.going([run("r8", "c2"), run("r1")]);
    names.going([run("r8", "c2")]);
    expect(again(names, "việc hai")).toBe(blind);
  });

  it("goes by what was going when the name first went out, however often it is sent again", () => {
    const names = sendNames();
    const first = unheard(names);
    names.going([run("r1")]);
    // Sent again while its turn is going, and nothing heard of that send either.
    const retry = names.take("c1", "tiếp tục", true);
    expect(retry.name).toBe(first);
    names.keep("c1", "tiếp tục", retry);
    names.going([]);
    expect(again(names)).not.toBe(first);
  });
});

describe("the name of a send nothing was heard of, as a stream read in its conversation says its turn is over", () => {
  it("is dropped when nothing was going there as the name went out", () => {
    const names = sendNames();
    const first = unheard(names);
    names.ended("c1");
    expect(again(names)).not.toBe(first);
  });

  it("is dropped all the same when turns were going in other conversations as the name went out", () => {
    const names = sendNames();
    names.going([run("r8", "c2"), run("r9", null)]);
    const first = unheard(names);
    names.ended("c1");
    expect(again(names)).not.toBe(first);
  });

  it("is kept when the stream was read in another conversation", () => {
    const names = sendNames();
    const first = unheard(names);
    names.ended("c2");
    expect(again(names)).toBe(first);
  });

  it("is kept when a turn was going there as the name went out: the end may be that turn's", () => {
    const names = sendNames();
    names.going([run("r0")]);
    const first = unheard(names);
    names.ended("c1");
    expect(again(names)).toBe(first);
  });

  it("is kept when the tab was reading a turn there as the name went out", () => {
    const names = sendNames();
    const first = unheard(names, "việc hai", true);
    names.ended("c1");
    expect(again(names, "việc hai")).toBe(first);
  });

  it("is kept when the turn ended before the send was known to have failed", () => {
    const names = sendNames();
    const sent = names.take("c1", "tiếp tục", false);
    names.ended("c1");
    names.keep("c1", "tiếp tục", sent);
    expect(again(names)).toBe(sent.name);
  });
});
