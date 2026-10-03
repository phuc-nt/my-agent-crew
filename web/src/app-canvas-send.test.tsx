import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "./i18n/vi";
import {
  bodies,
  box,
  conversation,
  openChat,
  openNote,
  posts,
  say,
  startApp,
  traffic,
  typeInCanvas,
} from "./test/canvas-app";
import { landed, stopServer, wait } from "./test/canvas-hook";
import type { FakeBackend } from "./test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = startApp();
});

afterEach(stopServer);

const everyPost = () => backend.requests.filter((r) => r.method === "POST" && r.path.endsWith("/messages"));

describe("sending a message while a canvas is open", () => {
  it("saves the typing in the canvas first, then sends the message naming that canvas", async () => {
    await openChat(1440);
    await openNote();
    typeInCanvas("bản sửa");

    await say("đọc lại giúp tôi");

    expect(traffic(backend).indexOf("PUT /artifacts/a1")).toBeGreaterThan(-1);
    expect(traffic(backend).indexOf("PUT /artifacts/a1")).toBeLessThan(
      traffic(backend).indexOf("POST /conversations/c1/messages"),
    );
    expect(bodies(backend)).toEqual([{ text: "đọc lại giúp tôi", canvas: { artifact_id: "a1", selection: null } }]);
    expect(backend.canvas.content("a1")).toBe("bản sửa");
  });

  it("names no canvas when none was opened in this tab", async () => {
    await openChat(1440);

    await say("chào");

    expect(bodies(backend)).toEqual([{ text: "chào" }]);
  });

  it("holds the words in a read-only box until the canvas is saved, and sends once however often Enter comes", async () => {
    await openChat(1440);
    await openNote();
    typeInCanvas("đang gõ");
    const release = backend.canvas.holdNext("PUT");

    await say("tin một");
    fireEvent.keyDown(box(), { key: "Enter" });
    fireEvent.keyDown(box(), { key: "Enter" });
    await landed();
    expect(posts(backend)).toHaveLength(0);
    expect(box()).toHaveAttribute("readonly");
    expect(box()).toHaveValue("tin một");

    await act(() => release());
    await landed();
    await landed();

    expect(posts(backend)).toHaveLength(1);
    expect(box()).toHaveValue("");
    expect(box()).not.toHaveAttribute("readonly");
  });

  it("says the canvas is being saved once the wait has gone on a moment, and stops when the message goes", async () => {
    await openChat(1440);
    await openNote();
    typeInCanvas("đang gõ");
    const release = backend.canvas.holdNext("PUT");

    await say("tin một");
    expect(screen.queryByText(vi.canvas.savingFirst)).toBeNull();
    wait(299);
    expect(screen.queryByText(vi.canvas.savingFirst)).toBeNull();
    wait(1);
    expect(screen.getByText(vi.canvas.savingFirst)).toHaveAttribute("role", "status");

    await act(() => release());
    await landed();
    await landed();

    expect(posts(backend)).toHaveLength(1);
    expect(screen.queryByText(vi.canvas.savingFirst)).toBeNull();
  });

  it("says nothing of saving when the canvas is saved at once", async () => {
    await openChat(1440);
    await openNote();
    typeInCanvas("đang gõ");

    await say("tin một");
    wait(1000);

    expect(posts(backend)).toHaveLength(1);
    expect(screen.queryByText(vi.canvas.savingFirst)).toBeNull();
  });

  it("sends the message all the same when the canvas could not be saved, and stops saying it is saving", async () => {
    await openChat(1440);
    await openNote();
    typeInCanvas("đang gõ");
    backend.canvas.refuseNext("PUT", 422);

    await say("tin một");

    expect(posts(backend)).toHaveLength(1);
    expect(screen.queryByText(vi.canvas.savingFirst)).toBeNull();
    expect(box()).toHaveValue("");
  });

  it("sends nothing when the person goes to another conversation before the save lands, and keeps the words", async () => {
    await openChat(1440);
    await openNote();
    typeInCanvas("đang gõ");
    const release = backend.canvas.holdNext("PUT");
    await say("tin dở");

    fireEvent.click(conversation("Hai"));
    await landed();
    await act(() => release());
    await landed();
    await landed();
    expect(everyPost()).toEqual([]);
    expect(box()).toHaveValue("");

    fireEvent.click(conversation("Một"));
    await landed();
    await landed();
    expect(box()).toHaveValue("tin dở");
    expect(box()).not.toHaveAttribute("readonly");
  });

  it("waits, in another conversation, for the save of the canvas the person left behind", async () => {
    await openChat(1440);
    await openNote();
    typeInCanvas("dở dang");
    const release = backend.canvas.holdNext("PUT");
    fireEvent.click(conversation("Hai"));
    await landed();
    await landed();

    await say("tin ở Hai");
    expect(posts(backend, "c2")).toEqual([]);
    await act(() => release());
    await landed();
    await landed();

    expect(traffic(backend).indexOf("PUT /artifacts/a1")).toBeLessThan(
      traffic(backend).indexOf("POST /conversations/c2/messages"),
    );
    expect(bodies(backend, "c2")).toEqual([{ text: "tin ở Hai" }]);
    expect(backend.canvas.content("a1")).toBe("dở dang");
  });
});

describe("a message the server turns down for the canvas it carried", () => {
  it("says in Vietnamese that the passage no longer fits, and leaves the words in the box", async () => {
    await openChat(1440);
    await openNote();
    const real = backend.fetch;
    vitest.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) =>
      String(input).endsWith("/messages")
        ? Promise.resolve(
            new Response(JSON.stringify({ detail: "the selection does not fit the canvas at version 3" }), {
              status: 422,
              headers: { "content-type": "application/json" },
            }),
          )
        : real(input, init),
    );

    await say("hỏi đoạn này");

    expect(screen.getByTestId("notice")).toHaveTextContent(vi.errorPrefix + vi.sendFailed.selection);
    expect(screen.queryByText(/does not fit/)).toBeNull();
    expect(box()).toHaveValue("hỏi đoạn này");
    expect(box()).not.toHaveAttribute("readonly");
    expect(screen.queryAllByTestId("message-user")).toEqual([]);
  });
});
