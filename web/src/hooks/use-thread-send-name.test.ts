import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { api } from "../api/client";
import type { AgentEvent, ConversationDetail } from "../api/types";
import type { SendNames, SentName } from "../lib/send-names";
import type { SendResult } from "../lib/send-result";
import { FakeBackend, storedMessage } from "../test/fake-backend";
import { memoryStorage } from "../test/memory-storage";
import { holdDraft, saveDraft } from "./use-draft";
import { type ThreadController, useThread } from "./use-thread";
import { useThreadSend } from "./use-thread-send";

/**
 * The name a send nothing was heard of goes out under when the same words are sent again, in
 * a thread that went on reading its conversation meanwhile: the same one until the page shows
 * the message as said, a new one from then on. And what becomes of the words the page handed
 * back, which a composer keeps as the conversation's draft.
 */

const WORDS = "tiếp tục";
const HEX = /^[0-9a-f]{32}$/;
const DONE: AgentEvent = { type: "done", spent_usd: 0, unknown_cost_calls: 0 };

const stored = (overrides: Partial<ConversationDetail> = {}) => new FakeBackend().create({ id: "c1", ...overrides });
const person = (text: string, id: string) => storedMessage("user", text, { id });
const answer = (text: string, id: string) => storedMessage("assistant", text, { id });
/** The conversation as the server has it once it took the message. */
const taken = () => stored({ messages: [person(WORDS, "m-taken")] });

type Thread = { current: ThreadController };

let store: Map<string, string>;
/** What reading c1 answers with now. */
let conversation: ConversationDetail;
/** What reading any other conversation answers with. */
let elsewhere: (id: string) => ConversationDetail;

const draft = () => store.get("composer-draft:c1");

beforeEach(() => {
  store = memoryStorage();
  conversation = stored();
  elsewhere = (id) => stored({ id });
  vitest.spyOn(api, "getConversation").mockImplementation(async (id) => (id === "c1" ? conversation : elsewhere(id)));
});

afterEach(() => {
  vitest.restoreAllMocks();
  vitest.unstubAllGlobals();
});

/** A thread open on c1 whose send of the words failed with nothing heard. Every later send
 *  is answered. `read: false` sends before the conversation's opening load has landed. */
async function unheard({ read = true }: { read?: boolean } = {}) {
  let lost = false;
  const sent = vitest.spyOn(api, "sendMessage").mockImplementation(async (_id, _text, onEvent) => {
    if (lost) return onEvent(DONE);
    lost = true;
    throw new TypeError("Failed to fetch");
  });
  const hook = renderHook(({ id }: { id: string }) => useThread(id), { initialProps: { id: "c1" } });
  if (read) await waitFor(() => expect(hook.result.current.state.conversationId).toBe("c1"));
  let outcome: SendResult | undefined;
  await act(async () => {
    outcome = await hook.result.current.send(WORDS);
  });
  expect(outcome?.status).toBe("failed");
  /** The names the sends went out under, in order. */
  const names = () => sent.mock.calls.map((call) => call[5]);
  return { ...hook, names };
}

async function sendAgain(thread: Thread) {
  await act(async () => {
    await thread.current.send(WORDS);
  });
}

/** The thread reads its conversation again and finds `now` there. */
async function readAgain(thread: Thread, now: ConversationDetail) {
  conversation = now;
  await act(async () => {
    await thread.current.reload();
  });
}

/** The thread reading along with a turn found going, whose stream the test holds. */
async function readAlong(thread: Thread, detail: ConversationDetail) {
  const turn: { emit: (e: AgentEvent) => void; end: () => void } = { emit: () => {}, end: () => {} };
  vitest.spyOn(api, "watchTurn").mockImplementation(
    (_id, emit) => new Promise<boolean>((resolve) => Object.assign(turn, { emit, end: () => resolve(true) })),
  );
  act(() => void thread.current.watch());
  await act(async () => turn.emit({ type: "watching", running: true, detail }));
  expect(thread.current.watching).toBe(true);
  return turn;
}

const kept = (names: () => (string | undefined)[]) => expect(names()[1]).toBe(names()[0]);
function renewed(names: () => (string | undefined)[]) {
  expect(names()[1]).toMatch(HEX);
  expect(names()[1]).not.toBe(names()[0]);
}

describe("the name of a send nothing was heard of, as the thread reads its conversation again", () => {
  it("is kept while the conversation does not show the message", async () => {
    const { result, names } = await unheard();
    await readAgain(result, stored({ messages: [person("việc khác", "m9"), answer("xong", "a9")] }));
    await sendAgain(result);
    kept(names);
  });

  it("is a new one once the conversation shows the message", async () => {
    const { result, names } = await unheard();
    await readAgain(result, taken());
    await sendAgain(result);
    renewed(names);
  });

  it("is a new one once the message shows waiting in line", async () => {
    const { result, names } = await unheard();
    await readAgain(result, stored({ queued: [{ id: 7, kind: "follow_up", text: WORDS }] }));
    await sendAgain(result);
    renewed(names);
  });

  it("is kept while the words show only as often as they did before the send", async () => {
    const before = [person(WORDS, "m0"), answer("được", "a0")];
    conversation = stored({ messages: before });
    const { result, names } = await unheard();
    await readAgain(result, stored({ messages: [...before, person("việc khác", "m9")] }));
    await sendAgain(result);
    kept(names);
  });

  it("is a new one once the words show one more time than before the send", async () => {
    const before = [person(WORDS, "m0"), answer("được", "a0")];
    conversation = stored({ messages: before });
    const { result, names } = await unheard();
    await readAgain(result, stored({ messages: [...before, person(WORDS, "m-taken")] }));
    await sendAgain(result);
    renewed(names);
  });

  it("is kept for a send made before the conversation had been read, whatever is read then", async () => {
    let land: (detail: ConversationDetail) => void = () => {};
    vitest.spyOn(api, "getConversation").mockImplementationOnce(() => new Promise((resolve) => (land = resolve)));
    conversation = taken();
    const { result, names } = await unheard({ read: false });
    // The opening load lands behind the send, so the thread reads the conversation once more.
    await act(async () => land(stored()));
    await waitFor(() => expect(result.current.state.conversationId).toBe("c1"));
    expect(result.current.state.items.map((item) => item.kind)).toEqual(["user"]);

    await sendAgain(result);
    kept(names);
  });

  it("is kept for its conversation while another one, opened meanwhile, shows the same words", async () => {
    elsewhere = (id) => stored({ id, messages: [person(WORDS, "x1")] });
    const { result, rerender, names } = await unheard();
    rerender({ id: "c2" });
    await waitFor(() => expect(result.current.state.conversationId).toBe("c2"));
    expect(result.current.state.items).toHaveLength(1);

    rerender({ id: "c1" });
    await waitFor(() => expect(result.current.state.conversationId).toBe("c1"));
    await sendAgain(result);
    kept(names);
  });

  it("is kept, with its words, as its conversation is opened while the one left still shows them", async () => {
    elsewhere = (id) => stored({ id, messages: [person(WORDS, "x1")] });
    const { result, rerender, names } = await unheard();
    saveDraft("c1", WORDS);
    rerender({ id: "c2" });
    await waitFor(() => expect(result.current.state.conversationId).toBe("c2"));

    // The thread left changes in the very render that asks for c1: what is on screen is
    // still the other conversation's, and says nothing of this one's message.
    act(() => {
      result.current.mutePreviews();
      rerender({ id: "c1" });
    });
    await waitFor(() => expect(result.current.state.conversationId).toBe("c1"));
    expect(draft()).toBe(WORDS);
    await sendAgain(result);
    kept(names);
  });
});

describe("the name of a send nothing was heard of, as the thread reads along with a turn", () => {
  it("is kept through a turn that never shows the message, to its end", async () => {
    const { result, names } = await unheard();
    const turn = await readAlong(result, stored());
    await act(async () => {
      turn.emit(DONE);
      turn.end();
    });
    await sendAgain(result);
    kept(names);
  });

  it("is a new one once the turn read along with shows the message", async () => {
    const { result, names } = await unheard();
    await readAlong(result, taken());
    await sendAgain(result);
    renewed(names);
  });
});

describe("the words handed back after a send nothing was heard of", () => {
  it("leave the conversation's draft once the thread shows the message", async () => {
    const { result } = await unheard();
    saveDraft("c1", WORDS);
    await readAgain(result, taken());
    expect(draft()).toBeUndefined();
  });

  it("stay in the draft while the thread does not show the message", async () => {
    const { result, names } = await unheard();
    saveDraft("c1", WORDS);
    await readAgain(result, stored());
    expect(draft()).toBe(WORDS);
    await sendAgain(result);
    kept(names);
  });

  it("are left as the person changed them, and are a new message from then on", async () => {
    const { result, names } = await unheard();
    saveDraft("c1", `${WORDS} nhé`);
    await readAgain(result, taken());
    expect(draft()).toBe(`${WORDS} nhé`);
    await sendAgain(result);
    renewed(names);
  });

  it("stay, with their name, while a send holds the box", async () => {
    const { result, names } = await unheard();
    saveDraft("c1", WORDS);
    const release = holdDraft("c1");
    try {
      await readAgain(result, taken());
      expect(draft()).toBe(WORDS);
      await sendAgain(result);
      kept(names);
    } finally {
      release();
    }
  });
});

describe("the count a name is taken with", () => {
  const sent: SentName = { name: "0".repeat(32), said: null };

  /** A send whose names the test watches, in a thread that counts as `said` says. */
  async function send(said?: (text: string) => number | null) {
    const names: SendNames = { take: vitest.fn(() => sent), keep: vitest.fn(), shown: vitest.fn(() => null), forget: vitest.fn() };
    const post = vitest.spyOn(api, "sendMessage").mockImplementation(async (_id, _text, onEvent) => onEvent(DONE));
    const runTurn = async (run: (emit: (e: AgentEvent) => void, signal: AbortSignal) => Promise<void>) => {
      await run(() => {}, new AbortController().signal);
    };
    const { result } = renderHook(() =>
      useThreadSend({ conversationId: "c1", busy: false, dispatch: vitest.fn(), runTurn, queueing: { current: new Set() }, names, said }),
    );
    await act(async () => {
      await result.current(WORDS);
    });
    expect(post.mock.calls[0][5]).toBe(sent.name);
    return names.take;
  }

  it("is how many times the page shows those words", async () => {
    const said = vitest.fn((_text: string) => 3);
    expect(await send(said)).toHaveBeenCalledWith("c1", WORDS, 3);
    expect(said).toHaveBeenCalledWith(WORDS);
  });

  it("is zero, and not unknown, for words the page does not show", async () => {
    expect(await send(() => 0)).toHaveBeenCalledWith("c1", WORDS, 0);
  });

  it("is unknown where the page cannot count", async () => {
    expect(await send(() => null)).toHaveBeenCalledWith("c1", WORDS, null);
  });

  it("is unknown where nothing counts for the send", async () => {
    expect(await send()).toHaveBeenCalledWith("c1", WORDS, null);
  });
});
