import type { Page } from "@playwright/test";

/**
 * A turn whose stream the test feeds a piece at a time.
 *
 * Playwright answers a route with the whole body at once, so a stream that is still going has to
 * be made in the page: the message the person posts to the conversation is answered there with a
 * body left open, and each `push` sends more events down it. The message never reaches the routes
 * of `mock-api`, so `posted` is the only place it can be read.
 */

type StreamEvent = Record<string, unknown> & { type: string };

type LiveTurn = {
  posted: unknown[];
  push(events: StreamEvent[]): void;
  close(): void;
};

type LivePage = { liveTurn: LiveTurn };

export type HeldTurn = {
  /** Sends `events` down the open stream together. */
  push(...events: StreamEvent[]): Promise<void>;
  /** Ends the stream, as the server does once the turn is over. */
  close(): Promise<void>;
  /** The bodies of the messages the page posted, oldest first. */
  posted(): Promise<unknown[]>;
};

/** Holds open the turn the next message to `conversationId` starts. Call before `page.goto`. */
export async function holdTurn(page: Page, conversationId: string): Promise<HeldTurn> {
  await page.addInitScript((id) => {
    const realFetch = window.fetch.bind(window);
    const encoder = new TextEncoder();
    let stream: ReadableStreamDefaultController<Uint8Array> | null = null;
    const turn: LiveTurn = {
      posted: [],
      push(events) {
        if (stream === null) throw new Error("no turn is open: the page has posted no message yet");
        for (const e of events) stream.enqueue(encoder.encode(`event: ${e.type}\r\ndata: ${JSON.stringify(e)}\r\n\r\n`));
      },
      close() {
        stream?.close();
        stream = null;
      },
    };
    (window as unknown as LivePage).liveTurn = turn;
    window.fetch = async (input, init) => {
      const posts = init?.method === "POST" && String(input).endsWith(`/api/conversations/${id}/messages`);
      if (!posts) return realFetch(input, init);
      turn.posted.push(JSON.parse(String(init?.body)));
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          stream = controller;
          init?.signal?.addEventListener("abort", () => {
            stream = null;
            controller.error(new DOMException("aborted", "AbortError"));
          });
        },
      });
      return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
    };
  }, conversationId);
  return {
    push: (...events) => page.evaluate((sent) => (window as unknown as LivePage).liveTurn.push(sent), events),
    close: () => page.evaluate(() => (window as unknown as LivePage).liveTurn.close()),
    posted: () => page.evaluate(() => (window as unknown as LivePage).liveTurn.posted),
  };
}
