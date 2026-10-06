import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentEvent, ConversationDetail } from "./api/types";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, FakeEventSource, fakeRun, storedMessage } from "./test/fake-backend";

/**
 * A send that failed with nothing heard hands its words back and keeps its name, so the same
 * words sent again are the same message. That lasts while the page says the send failed. Once
 * the thread shows the message as said, the page takes the handed-back words out of the box and
 * lets the name go: what is typed after that is a new message, the next step the person asks for.
 */

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  FakeEventSource.instances = [];
  vitest.stubGlobal("fetch", backend.fetch);
  vitest.stubGlobal("EventSource", FakeEventSource);
  window.location.hash = "";
  window.localStorage.clear();
});

afterEach(() => vitest.unstubAllGlobals());

type Sent = { text: string; request_id: string };

/** A door the test opens by hand: what waits behind it happens only then. */
function door() {
  let open = () => {};
  const shut = new Promise<void>((resolve) => (open = resolve));
  return { shut, open };
}

const isSend = (input: RequestInfo | URL, init?: RequestInit) => init?.method === "POST" && String(input).endsWith("/messages");

/** The server takes the next message and the connection drops before it answers: at once, or
 *  when `cut` opens. `load` keeps back the first read of the conversation `of`. */
function loseAnswer({ cut, load, of }: { cut?: { shut: Promise<void> }; load?: { shut: Promise<void> }; of?: string } = {}) {
  let lost = false;
  let held = false;
  vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    const response = await backend.fetch(input, init);
    if (load && !held && !init?.method && String(input).endsWith(`/conversations/${of}`)) {
      held = true;
      await load.shut;
      return response;
    }
    if (!isSend(input, init) || lost) return response;
    lost = true;
    await cut?.shut;
    void response.body?.cancel();
    throw new TypeError("Failed to fetch");
  });
}

/** The next message never reaches the server. Answers with what it was sent as. */
function neverArrives(): Sent[] {
  const unsent: Sent[] = [];
  vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    if (!isSend(input, init) || unsent.length > 0) return backend.fetch(input, init);
    unsent.push(JSON.parse(String(init?.body)) as Sent);
    throw new TypeError("Failed to fetch");
  });
  return unsent;
}

const open = async (title: string) => {
  await userEvent.click(await screen.findByRole("button", { name: new RegExp(title) }));
  await screen.findByRole("heading", { level: 1, name: title });
};

/** The page on the conversation, its activity stream open on a server where nothing is going. */
async function openConversation(title: string) {
  render(<App />);
  await open(title);
  const stream = FakeEventSource.instances.at(-1)!;
  act(() => {
    stream.open();
    stream.emit({ type: "snapshot", runs: [] });
  });
  return stream;
}

const box = () => screen.getByRole("textbox", { name: vi.composerPlaceholder });
const bubbles = () => screen.queryAllByTestId("message-user").map((b) => b.querySelector("p")?.textContent);
const sends = (id: string) =>
  backend.requests.filter((r) => r.method === "POST" && r.path === `/conversations/${id}/messages`).map((r) => r.body as Sent);
const reads = (id: string) => backend.requests.filter((r) => r.method === "GET" && r.path === `/conversations/${id}`).length;
/** What the server stored as said by the person, in order. */
const said = (c: ConversationDetail) => c.messages.filter((m) => m.role === "user").map((m) => m.content);
const answer = (content: string, id: string): AgentEvent[] => [
  { type: "assistant_message", message_id: id, content, tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
  { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
];
const going = (id: string, conversation: string, source = "chat") => fakeRun({ id, conversation_id: conversation, source, status: "running", finished_at: null });
const over = (id: string, conversation: string, source = "chat") => fakeRun({ id, conversation_id: conversation, source, status: "done" });

/** Waits for the failure that hands the words back. */
async function handedBack(text: string) {
  // The box holds the words all through a send: it is the notice that says the send failed.
  await waitFor(() => expect(screen.getByTestId("notice")).toHaveTextContent(vi.requestErrors.network));
  expect(box()).toHaveValue(text);
}

/** Sends `text`, and waits for the failure that hands the words back. */
async function sendUnheard(text: string) {
  await userEvent.type(box(), `${text}{Enter}`);
  await handedBack(text);
}

/** What the box holds in the frame `text` first shows as said. The page is read as it
 *  changes, ahead of anything that runs once the frame is drawn. */
function boxAsShown(text: string) {
  let held: string | null = null;
  const watcher = new MutationObserver(() => {
    if (held === null && bubbles().includes(text)) held = (box() as HTMLTextAreaElement).value;
  });
  watcher.observe(document.body, { childList: true, subtree: true, characterData: true });
  return () => {
    watcher.disconnect();
    return held;
  };
}

/** Presses Enter on the box as it is, and gives a request it would make the time to go out. */
async function pressEnter() {
  await userEvent.type(box(), "{Enter}");
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
}

describe("a message the server took and whose answer was lost, once the thread shows it said", () => {
  it("leaves the box when the page reads along with the turn it started, and is not sent twice", async () => {
    const c = backend.create({ title: "Đọc theo lượt" });
    loseAnswer();
    const stream = await openConversation("Đọc theo lượt");
    await sendUnheard("tiếp tục");
    expect(bubbles()).toEqual([]);
    const turn = backend.serveTurn(c.id, { writing: [{ type: "text_delta", text: "đang làm bước một" }], stoppable: true });
    const heldAsShown = boxAsShown("tiếp tục");

    act(() => stream.emit({ type: "run", run: going("r1", c.id) }));

    // The page shows the message as said: nothing is left to send again, and no failure to
    // answer. The words leave the box in the frame the message shows in, not one later.
    await waitFor(() => expect(bubbles()).toEqual(["tiếp tục"]));
    expect(heldAsShown()).toBe("");
    expect(box()).toHaveValue("");
    expect(screen.queryByTestId("notice")).not.toBeInTheDocument();
    expect(await screen.findByTestId("streaming")).toHaveTextContent("đang làm bước một");
    await pressEnter();
    expect(sends(c.id)).toHaveLength(1);

    c.messages.push(storedMessage("assistant", "Xong bước một.", { id: "a1" }));
    await act(async () => {
      turn.push(answer("Xong bước một.", "a1"));
      turn.end();
    });
    act(() => stream.emit({ type: "run", run: over("r1", c.id) }));
    await waitFor(() => expect(screen.queryByTestId("streaming")).not.toBeInTheDocument());
    expect(await screen.findByTestId("message-assistant")).toHaveTextContent("Xong bước một.");
    expect(box()).toHaveValue("");
    expect(sends(c.id)).toHaveLength(1);
    expect(said(c)).toEqual(["tiếp tục"]);
  });

  it("leaves the box when the conversation is read again after its run, and the same words typed anew are a new message", async () => {
    const c = backend.create({ title: "Chỉ biết đã xong" });
    loseAnswer();
    const stream = await openConversation("Chỉ biết đã xong");
    await sendUnheard("tiếp tục");
    // The run is known to be going, and the server has no turn there to read along with.
    act(() => stream.emit({ type: "run", run: going("r1", c.id) }));
    await waitFor(() => expect(backend.requests.some((r) => r.method === "GET" && r.path === `/conversations/${c.id}/turn`)).toBe(true));
    expect(box()).toHaveValue("tiếp tục"); // nothing shows it said yet

    c.messages.push(storedMessage("assistant", "Xong bước một.", { id: "a1" }));
    act(() => stream.emit({ type: "run", run: over("r1", c.id) }));

    expect(await screen.findByTestId("message-assistant")).toHaveTextContent("Xong bước một.");
    expect(bubbles()).toEqual(["tiếp tục"]);
    expect(box()).toHaveValue("");
    await pressEnter();
    expect(sends(c.id)).toHaveLength(1);

    // The person reads the answer and asks for the next step in the same words.
    backend.nextTurn = answer("Xong bước hai.", "a2");
    await userEvent.type(box(), "tiếp tục{Enter}");

    await waitFor(() => expect(sends(c.id)).toHaveLength(2));
    expect(sends(c.id)[1].text).toBe("tiếp tục");
    expect(sends(c.id)[1].request_id).toMatch(/^[0-9a-f]{32}$/);
    expect(sends(c.id)[1].request_id).not.toBe(sends(c.id)[0].request_id);
    await waitFor(() => expect(screen.getAllByTestId("message-assistant")).toHaveLength(2));
    expect(screen.getAllByTestId("message-assistant")[1]).toHaveTextContent("Xong bước hai.");
    expect(said(c)).toEqual(["tiếp tục", "tiếp tục"]);
    expect(box()).toHaveValue("");
  });

  it("is said once when the tab hears that its run ended and that its send failed in one breath", async () => {
    const c = backend.create({ title: "Xong rồi mới biết lỗi" });
    const cut = door();
    loseAnswer({ cut });
    const stream = await openConversation("Xong rồi mới biết lỗi");
    await userEvent.type(box(), "tiếp tục{Enter}");
    await waitFor(() => expect(sends(c.id)).toHaveLength(1));
    act(() => stream.emit({ type: "run", run: going("r1", c.id) }));
    // The turn ran to its end on the server while the answer was on its way.
    c.messages.push(storedMessage("assistant", "Xong bước một.", { id: "a1" }));

    await act(async () => {
      stream.emit({ type: "run", run: over("r1", c.id) });
      cut.open();
      // The failure reaches the tab before the page has drawn the end of the run.
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    // The run ended as nobody's, so the conversation is read again: the page shows the message
    // and its answer, and pressing send on what the box holds by then does not say it twice.
    expect(await screen.findByTestId("message-assistant")).toHaveTextContent("Xong bước một.");
    await pressEnter();
    expect(said(c)).toEqual(["tiếp tục"]);
    expect(sends(c.id)).toHaveLength(1);
    expect(bubbles()).toEqual(["tiếp tục"]);
    expect(box()).toHaveValue("");
    expect(screen.queryByTestId("notice")).not.toBeInTheDocument();
    expect(screen.getAllByTestId("message-assistant")).toHaveLength(1);
  });

  it("is said once when the tab saw its run end before it heard that the send failed", async () => {
    const c = backend.create({ title: "Xong trước khi biết lỗi" });
    const cut = door();
    loseAnswer({ cut });
    const stream = await openConversation("Xong trước khi biết lỗi");
    await userEvent.type(box(), "tiếp tục{Enter}");
    await waitFor(() => expect(sends(c.id)).toHaveLength(1));
    act(() => stream.emit({ type: "run", run: going("r1", c.id) }));
    c.messages.push(storedMessage("assistant", "Xong bước một.", { id: "a1" }));
    act(() => stream.emit({ type: "run", run: over("r1", c.id) }));

    await act(async () => cut.open());

    // The run ended as this tab's own, so nothing reads the conversation again: the page
    // says only that the send failed, and holds the words to send again.
    await handedBack("tiếp tục");
    expect(bubbles()).toEqual([]);
    expect(reads(c.id)).toBe(1);

    await pressEnter();

    expect(await screen.findByTestId("message-assistant")).toHaveTextContent("Xong bước một.");
    await waitFor(() => expect(box()).toHaveValue(""));
    expect(bubbles()).toEqual(["tiếp tục"]);
    expect(sends(c.id)).toHaveLength(2);
    expect(sends(c.id)[1]).toEqual(sends(c.id)[0]);
    expect(said(c)).toEqual(["tiếp tục"]);
  });

  it("leaves a box the person has changed alone, and the first words sent after that are a new message", async () => {
    const c = backend.create({ title: "Đã sửa chữ" });
    loseAnswer();
    const stream = await openConversation("Đã sửa chữ");
    await sendUnheard("tiếp tục");
    await userEvent.type(box(), " nhé");
    c.messages.push(storedMessage("assistant", "Xong bước một.", { id: "a1" }));
    act(() => stream.emit({ type: "run", run: going("r1", c.id) }));
    await waitFor(() => expect(backend.requests.some((r) => r.method === "GET" && r.path === `/conversations/${c.id}/turn`)).toBe(true));

    act(() => stream.emit({ type: "run", run: over("r1", c.id) }));

    expect(await screen.findByTestId("message-assistant")).toHaveTextContent("Xong bước một.");
    expect(bubbles()).toEqual(["tiếp tục"]);
    expect(box()).toHaveValue("tiếp tục nhé"); // the person's, not the page's to take

    backend.nextTurn = answer("Xong bước hai.", "a2");
    await userEvent.clear(box());
    await userEvent.type(box(), "tiếp tục{Enter}");

    await waitFor(() => expect(sends(c.id)).toHaveLength(2));
    expect(sends(c.id)[1].request_id).not.toBe(sends(c.id)[0].request_id);
    await waitFor(() => expect(said(c)).toEqual(["tiếp tục", "tiếp tục"]));
  });
});

describe("a message the server put in line and whose answer was lost", () => {
  /** "việc hai" was sent while the turn of "việc một" was going, and nothing was heard of it. */
  async function waitingBehind(title: string) {
    const c = backend.create({ title });
    const held = backend.holdTurn(c.id);
    const stream = await openConversation(title);
    await userEvent.type(box(), "việc một{Enter}");
    act(() => stream.emit({ type: "run", run: going("r1", c.id) }));
    await act(async () => held.push([{ type: "text_delta", text: "đang làm việc một" }]));
    expect(await screen.findByTestId("streaming")).toHaveTextContent("đang làm việc một");
    loseAnswer();
    await sendUnheard("việc hai");
    expect(c.queued).toHaveLength(1); // the server holds it; this tab was never told
    expect(screen.queryByRole("list", { name: vi.queuedLabel })).not.toBeInTheDocument();
    return { c, held, stream };
  }

  it("leaves the box once the page reads along with the turn that took it, and is not sent twice", async () => {
    const { c, held, stream } = await waitingBehind("Đang tới lượt");
    c.messages.push(storedMessage("assistant", "Xong việc một.", { id: "a1" }));
    await act(async () => {
      held.push(answer("Xong việc một.", "a1"));
      held.release();
    });
    await waitFor(() => expect(screen.queryByRole("button", { name: vi.stop })).not.toBeInTheDocument());
    expect(box()).toHaveValue("việc hai"); // its turn has not been seen yet
    backend.drain(c.id);
    backend.serveTurn(c.id, { writing: [{ type: "text_delta", text: "đang làm việc hai" }], stoppable: true });
    const heldAsShown = boxAsShown("việc hai");

    act(() => stream.emit({ type: "run", run: over("r1", c.id) }));
    act(() => stream.emit({ type: "run", run: going("r2", c.id) }));

    await waitFor(() => expect(bubbles()).toEqual(["việc một", "việc hai"]));
    expect(heldAsShown()).toBe("");
    expect(box()).toHaveValue("");
    expect(await screen.findByTestId("streaming")).toHaveTextContent("đang làm việc hai");
    await pressEnter();
    expect(sends(c.id)).toHaveLength(2);
    expect(said(c)).toEqual(["việc một", "việc hai"]);
  });

  it("leaves the box of its conversation once the page shows it waiting in line", async () => {
    backend.create({ title: "Chỗ khác" });
    const { c, held } = await waitingBehind("Còn chờ");
    await open("Chỗ khác");
    expect(box()).toHaveValue("");

    await open("Còn chờ");

    const chips = await screen.findByRole("list", { name: vi.queuedLabel });
    expect(within(chips).getAllByRole("listitem")).toHaveLength(1);
    expect(chips).toHaveTextContent("việc hai");
    expect(box()).toHaveValue("");
    await pressEnter();
    expect(sends(c.id)).toHaveLength(2);
    expect(c.queued).toHaveLength(1);
    await act(async () => held.release());
  });
});

describe("the name kept for a send nothing was heard of", () => {
  it("is still its name after a message sent in another conversation", async () => {
    const a = backend.create({ title: "Hội thoại A" });
    const b = backend.create({ title: "Hội thoại B" });
    const unsent = neverArrives();
    await openConversation("Hội thoại A");
    await sendUnheard("làm đi");
    expect(unsent).toHaveLength(1);

    await open("Hội thoại B");
    backend.nextTurn = answer("Chào bạn.", "b1");
    await userEvent.type(box(), "chào B{Enter}");
    expect(await screen.findByTestId("message-assistant")).toHaveTextContent("Chào bạn.");
    expect(sends(b.id)).toHaveLength(1);

    await open("Hội thoại A");
    expect(box()).toHaveValue("làm đi");
    backend.nextTurn = answer("Xong rồi.", "a1");
    await pressEnter();

    expect(await screen.findByTestId("message-assistant")).toHaveTextContent("Xong rồi.");
    expect(sends(a.id)).toHaveLength(1);
    expect(sends(a.id)[0]).toMatchObject(unsent[0]);
    expect(said(a)).toEqual(["làm đi"]);
  });

  it("is not let go by an earlier message of the same words that the page already showed", async () => {
    const c = backend.create({ title: "Hai lần tiếp tục" });
    const stream = await openConversation("Hai lần tiếp tục");
    backend.nextTurn = answer("Xong bước một.", "a1");
    await userEvent.type(box(), "tiếp tục{Enter}");
    expect(await screen.findByTestId("message-assistant")).toHaveTextContent("Xong bước một.");
    c.messages.push(storedMessage("assistant", "Xong bước một.", { id: "a1" }));
    await waitFor(() => expect(box()).toHaveValue(""));
    const unsent = neverArrives();
    await sendUnheard("tiếp tục");
    expect(bubbles()).toEqual(["tiếp tục"]); // the first one, still as this tab wrote it

    // A turn from elsewhere comes and goes, and the conversation is read again: the first
    // message is the server's now, and the second is nowhere.
    act(() => stream.emit({ type: "run", run: going("r9", c.id, "job") }));
    await waitFor(() => expect(backend.requests.some((r) => r.method === "GET" && r.path === `/conversations/${c.id}/turn`)).toBe(true));
    const before = reads(c.id);
    act(() => stream.emit({ type: "run", run: over("r9", c.id, "job") }));
    await waitFor(() => expect(reads(c.id)).toBe(before + 1));
    await act(async () => {});

    expect(bubbles()).toEqual(["tiếp tục"]);
    expect(box()).toHaveValue("tiếp tục");
    backend.nextTurn = answer("Xong bước hai.", "a2");
    await pressEnter();

    await waitFor(() => expect(sends(c.id)).toHaveLength(2));
    expect(sends(c.id)[1]).toMatchObject(unsent[0]);
    await waitFor(() => expect(said(c)).toEqual(["tiếp tục", "tiếp tục"]));
    await waitFor(() => expect(box()).toHaveValue(""));
  });

  it("is kept for a message sent before the conversation had been read, and sent again changes nothing on a screen that reads its turn", async () => {
    const c = backend.create({ title: "Gửi sớm" });
    const load = door();
    loseAnswer({ load, of: c.id });
    const stream = await openConversation("Gửi sớm");
    await sendUnheard("làm đi");
    // The opening read lands behind the message, so the conversation is read again: the page
    // shows the message, and has nothing to tell it from one that was there all along.
    await act(async () => load.open());
    await waitFor(() => expect(bubbles()).toEqual(["làm đi"]));
    expect(box()).toHaveValue("làm đi");
    const turn = backend.serveTurn(c.id, { writing: [{ type: "text_delta", text: "đang làm" }], stoppable: true });
    act(() => stream.emit({ type: "run", run: going("r1", c.id) }));
    expect(await screen.findByTestId("streaming")).toHaveTextContent("đang làm");
    expect(box()).toHaveValue("làm đi");

    await userEvent.type(box(), "{Enter}");

    await waitFor(() => expect(box()).toHaveValue(""));
    // The second request was let go as soon as the server said the message had arrived.
    await waitFor(() => expect(turn.watchers()).toBe(1));
    expect(screen.getByTestId("streaming")).toHaveTextContent("đang làm");
    expect(bubbles()).toEqual(["làm đi"]);
    expect(screen.queryByRole("list", { name: vi.queuedLabel })).not.toBeInTheDocument();
    expect(said(c)).toEqual(["làm đi"]);
    expect(sends(c.id)[1].request_id).toBe(sends(c.id)[0].request_id);
  });
});

describe("words a failed send handed back in a conversation the person then left", () => {
  it("are gone from its box on return, once the conversation shows the message", async () => {
    const a = backend.create({ title: "Hội thoại A" });
    backend.create({ title: "Hội thoại B" });
    loseAnswer();
    await openConversation("Hội thoại A");
    await sendUnheard("làm đi");
    a.messages.push(storedMessage("assistant", "Xong rồi.", { id: "a1" }));

    await open("Hội thoại B");
    expect(box()).toHaveValue("");
    await open("Hội thoại A");

    expect(await screen.findByTestId("message-assistant")).toHaveTextContent("Xong rồi.");
    expect(bubbles()).toEqual(["làm đi"]);
    expect(box()).toHaveValue("");
    await pressEnter();
    expect(sends(a.id)).toHaveLength(1);
    expect(said(a)).toEqual(["làm đi"]);
  });
});
