import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, storedMessage } from "./test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  vitest.stubGlobal("fetch", backend.fetch);
  window.location.hash = "";
});

afterEach(() => vitest.unstubAllGlobals());

const FULL = "Hàng chờ của cuộc trò chuyện này đã đủ 20 tin. Đợi lượt hiện tại xong rồi gửi tiếp.";

/** Answers every POST to /messages with a refusal, and everything else as the fake does. */
function refuseMessages(status: number, detail: string) {
  vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) =>
    init?.method === "POST" && String(input).endsWith("/messages")
      ? new Response(JSON.stringify({ detail }), { status, headers: { "content-type": "application/json" } })
      : backend.fetch(input, init),
  );
}

async function openConversation(title: string) {
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: new RegExp(title) }));
  await screen.findByRole("heading", { level: 1, name: title });
}

const box = () => screen.getByRole("textbox");
// The words of each message from the person, without the screen-reader label beside them.
const bubbles = () => screen.queryAllByTestId("message-user").map((b) => b.querySelector("p")?.textContent);

describe("a message sent while this tab thought the conversation idle", () => {
  it("stays out of the box once the server queued it: the chip stands for it", async () => {
    const c = backend.create({ title: "Bận nơi khác", messages: [storedMessage("user", "chào")] });
    await openConversation("Bận nơi khác");
    // Another tab's turn is running, which this tab cannot see: it has no stream of its own,
    // so it sends as if idle and the server answers with a single `queued` event.
    const held = backend.holdTurn(c.id);
    await backend.fetch(`/api/conversations/${c.id}/messages`, {
      method: "POST",
      body: JSON.stringify({ text: "việc của tab kia" }),
    });

    await userEvent.type(box(), "việc nối tiếp{Enter}");
    const chips = await screen.findByRole("list", { name: vi.queuedLabel });
    // Whatever the send does once the server has answered has happened by here.
    await act(async () => {});

    expect(chips).toHaveTextContent("việc nối tiếp");
    expect(box()).toHaveValue("");
    expect(bubbles()).toEqual(["chào"]);
    held.release();
  });

  it("takes its bubble back and leaves the words in the box when the server refuses it before saying anything", async () => {
    backend.create({ title: "Hàng đầy", messages: [storedMessage("user", "chào")] });
    refuseMessages(429, FULL);
    await openConversation("Hàng đầy");

    await userEvent.type(box(), "chưa tới được server{Enter}");
    expect(await screen.findByTestId("notice")).toHaveTextContent(FULL);
    await act(async () => {});

    expect(box()).toHaveValue("chưa tới được server");
    expect(bubbles()).toEqual(["chào"]);
  });

  it("hands the first message of a new conversation back to the box when it cannot be sent", async () => {
    refuseMessages(429, FULL);
    render(<App />);
    await screen.findByText(vi.welcomeTitleFor("Agent"));

    await userEvent.type(box(), "câu mở đầu{Enter}");
    expect(await screen.findByTestId("notice")).toHaveTextContent(FULL);
    await act(async () => {});

    expect(backend.conversations.size).toBe(1);
    expect(box()).toHaveValue("câu mở đầu");
    expect(bubbles()).toEqual([]);
  });
});
