import { describe, expect, it, vi as vitest } from "vitest";
import type { QueuedMessage } from "../api/types";
import type { ThreadItem } from "../state/thread-reducer";
import { sendNames, timesSaid, type SendNames, type SentName } from "./send-names";

const HEX = /^[0-9a-f]{32}$/;
const WORDS = "tiếp tục";

const person = (text: string, id = "m1"): ThreadItem => ({ kind: "user", id, text });
const answer = (text: string, id = "a1"): ThreadItem => ({ kind: "assistant", id, text, model: null });
const note = (text: string, id = "n1"): ThreadItem => ({ kind: "note", id, text });
const inLine = (text: string, id = 1, kind: QueuedMessage["kind"] = "follow_up"): QueuedMessage => ({ id, kind, text });
const thread = (items: ThreadItem[] = [], waiting: QueuedMessage[] = []) => ({ items, waiting });

/** A send to c1 that nothing was heard of, made when the page showed the words `said` times. */
function unheard(names: SendNames, said: number | null = 0, text = WORDS): SentName {
  const sent = names.take("c1", text, said);
  names.keep("c1", text, sent);
  return sent;
}

/** The name the same words would go out to c1 under now. Asking spends a kept name. */
const again = (names: SendNames, text = WORDS) => names.take("c1", text, 0).name;
/** The words the page is told to take back when it shows the kept ones `times` times. */
const shownAt = (names: SendNames, times: number, conversation = "c1") => names.shown(conversation, () => times);

describe("how many times a thread shows words as said by the person", () => {
  it("counts the person's messages of those very words", () => {
    expect(timesSaid(thread([person(WORDS, "m1"), answer("được"), person(WORDS, "m2")]), WORDS)).toBe(2);
  });

  it("counts this tab's own message that is not stored yet", () => {
    expect(timesSaid(thread([person(WORDS, "local-0")]), WORDS)).toBe(1);
  });

  it("counts the same words waiting in line, whatever they wait as", () => {
    expect(timesSaid(thread([person(WORDS)], [inLine(WORDS, 1), inLine(WORDS, 2, "steer")]), WORDS)).toBe(3);
  });

  it("does not count an answer or a note of the same words", () => {
    expect(timesSaid(thread([answer(WORDS), note(WORDS)]), WORDS)).toBe(0);
  });

  it("does not count a message, or one waiting in line, that only holds the words", () => {
    const messages = [person(`${WORDS} nhé`, "m1"), person(` ${WORDS}`, "m2")];
    expect(timesSaid(thread(messages, [inLine(`${WORDS}\n\n${WORDS}`)]), WORDS)).toBe(0);
  });

  it("is zero for a thread that shows nothing", () => {
    expect(timesSaid(thread(), WORDS)).toBe(0);
  });
});

describe("the name a message is sent under", () => {
  it("is a new one for each send, and carries how the page stood", () => {
    const names = sendNames();
    const first = names.take("c1", "chào", 2);
    expect(first.name).toMatch(HEX);
    expect(first.said).toBe(2);
    const second = names.take("c1", "chào", null);
    expect(second.name).toMatch(HEX);
    expect(second.name).not.toBe(first.name);
    expect(second.said).toBeNull();
  });

  it("is kept for the same words to the same conversation after a send nothing was heard of", () => {
    const names = sendNames();
    const first = unheard(names, 1);
    // The page may stand otherwise by now: the name goes out as it first did.
    expect(names.take("c1", WORDS, 4)).toEqual(first);
  });

  it("is spent by the send that takes it", () => {
    const names = sendNames();
    const first = unheard(names);
    expect(again(names)).toBe(first.name);
    // Nothing kept it this time: the words are a new message from here on.
    expect(again(names)).not.toBe(first.name);
  });

  it("is kept again by each send that is not heard back either", () => {
    const names = sendNames();
    const first = unheard(names, 1);
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const next = names.take("c1", WORDS, 5);
      expect(next).toEqual(first);
      names.keep("c1", WORDS, next);
    }
    expect(shownAt(names, 1)).toBeNull();
    expect(shownAt(names, 2)).toBe(WORDS);
  });

  it("is let go by other words, and does not come back after them", () => {
    const names = sendNames();
    const first = unheard(names);
    expect(again(names, `${WORDS} nhé`)).not.toBe(first.name);
    expect(again(names)).not.toBe(first.name);
  });

  it("is neither taken nor let go by a send to another conversation", () => {
    const names = sendNames();
    const first = unheard(names);
    expect(names.take("c2", WORDS, 0).name).not.toBe(first.name);
    expect(again(names)).toBe(first.name);
  });

  it("is kept for each conversation by itself", () => {
    const names = sendNames();
    const first = unheard(names);
    const other = names.take("c2", WORDS, 0);
    names.keep("c2", WORDS, other);
    expect(other.name).not.toBe(first.name);
    expect(names.take("c2", WORDS, 0).name).toBe(other.name);
    expect(again(names)).toBe(first.name);
  });

  it("is that of the last unheard send only, in one conversation", () => {
    const names = sendNames();
    const first = unheard(names, 0, "một");
    const second = unheard(names, 0, "hai");
    expect(shownAt(names, 1)).toBe("hai");
    expect(again(names, "hai")).toBe(second.name);
    expect(again(names, "một")).not.toBe(first.name);
  });
});

describe("a kept name whose message the page shows", () => {
  it("is not shown while the page shows the words as often as when the name first went out", () => {
    const names = sendNames();
    unheard(names, 1);
    expect(shownAt(names, 1)).toBeNull();
  });

  it("is not shown when the page shows the words less often", () => {
    const names = sendNames();
    unheard(names, 2);
    expect(shownAt(names, 1)).toBeNull();
    expect(shownAt(names, 0)).toBeNull();
  });

  it("is shown once the page shows the words one more time", () => {
    const names = sendNames();
    unheard(names, 1);
    expect(shownAt(names, 2)).toBe(WORDS);
  });

  it("is shown for words the page had never shown", () => {
    const names = sendNames();
    unheard(names, 0);
    expect(shownAt(names, 0)).toBeNull();
    expect(shownAt(names, 1)).toBe(WORDS);
  });

  it("is never shown when the page could not count as the name first went out", () => {
    const names = sendNames();
    unheard(names, null);
    expect(shownAt(names, 0)).toBeNull();
    expect(shownAt(names, 1)).toBeNull();
    expect(shownAt(names, 9)).toBeNull();
  });

  it("is counted by the kept words", () => {
    const names = sendNames();
    unheard(names, 0);
    const said = vitest.fn((_text: string) => 0);
    names.shown("c1", said);
    expect(said).toHaveBeenCalledTimes(1);
    expect(said).toHaveBeenCalledWith(WORDS);
  });

  it("is nothing where no name is kept, and the thread is not counted there", () => {
    const names = sendNames();
    const said = vitest.fn((_text: string) => 9);
    expect(names.shown("c1", said)).toBeNull();
    unheard(names, 0);
    expect(names.shown("c2", said)).toBeNull();
    expect(said).not.toHaveBeenCalled();
  });

  it("is not let go by being asked about", () => {
    const names = sendNames();
    const first = unheard(names, 0);
    expect(shownAt(names, 1)).toBe(WORDS);
    expect(shownAt(names, 1)).toBe(WORDS);
    expect(again(names)).toBe(first.name);
  });

  it("is not shown while a send of the words is on its way again", () => {
    const names = sendNames();
    unheard(names, 0);
    names.take("c1", WORDS, 0);
    expect(shownAt(names, 1)).toBeNull();
  });

  it("is let go when told to forget", () => {
    const names = sendNames();
    const first = unheard(names, 0);
    names.forget("c1");
    expect(shownAt(names, 1)).toBeNull();
    expect(again(names)).not.toBe(first.name);
  });

  it("is forgotten for that conversation only", () => {
    const names = sendNames();
    unheard(names, 0);
    const other = names.take("c2", "việc khác", 0);
    names.keep("c2", "việc khác", other);
    names.forget("c1");
    expect(shownAt(names, 1, "c2")).toBe("việc khác");
    expect(names.take("c2", "việc khác", 0).name).toBe(other.name);
  });
});
