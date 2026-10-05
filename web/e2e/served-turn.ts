import type { Page } from "@playwright/test";

/**
 * A turn the page did not start, and the activity stream that tells the page about it.
 *
 * Both are made in the page, for the reason `live-stream.ts` gives: Playwright answers a route
 * with its whole body at once, and these two are read while they are still being written. Each
 * helper must be called before `page.goto`, and is in place again after a reload, as a server
 * that kept the turn going would be.
 */

type StreamEvent = Record<string, unknown> & { type: string };

type Served = {
  written: StreamEvent[];
  watchers: number;
  stops: number;
  push(events: StreamEvent[]): void;
  end(): void;
};

type Activity = { open: boolean; emit(payloads: StreamEvent[]): void };

type ServedPage = { servedTurn: Served; liveActivity: Activity };

export type ServedTurn = {
  /** What the turn has written since its last stored message: handed to whoever joins from now on. */
  write(...events: StreamEvent[]): Promise<void>;
  /** Sends `events` to every reader of the turn. */
  push(...events: StreamEvent[]): Promise<void>;
  /** Ends the turn: its readers' streams end, and the server has no turn left to read. */
  end(): Promise<void>;
  /** How many streams are reading along now. */
  watchers(): Promise<number>;
  /** How many times the page told the server to stop this turn. */
  stops(): Promise<number>;
};

/**
 * A turn under way in `conversationId`. `GET …/turn` hands whoever asks the conversation as
 * `mock-api` has it stored at that moment, then `writing`, then whatever `push` sends.
 * `stoppable` is a turn the server reads itself, which `POST …/stop` ends; any other is its
 * own reader's, and the stop goes on to `mock-api`, which says it ended nothing.
 */
export async function serveTurn(
  page: Page,
  conversationId: string,
  options: { writing?: StreamEvent[]; stoppable?: boolean } = {},
): Promise<ServedTurn> {
  await page.addInitScript(
    ({ id, writing, stoppable }) => {
      const realFetch = window.fetch.bind(window);
      const encoder = new TextEncoder();
      const frame = (e: StreamEvent) => encoder.encode(`event: ${e.type}\r\ndata: ${JSON.stringify(e)}\r\n\r\n`);
      const streams = new Set<ReadableStreamDefaultController<Uint8Array>>();
      let going = true;
      const turn: Served = {
        written: writing,
        stops: 0,
        get watchers() {
          return streams.size;
        },
        push(events) {
          for (const stream of streams) for (const e of events) stream.enqueue(frame(e));
        },
        end() {
          going = false;
          for (const stream of streams) stream.close();
          streams.clear();
        },
      };
      (window as unknown as ServedPage).servedTurn = turn;
      const base = `/api/conversations/${id}`;
      window.fetch = async (input, init) => {
        const url = String(input instanceof Request ? input.url : input);
        const method = init?.method ?? "GET";
        if (going && stoppable && method === "POST" && url.endsWith(`${base}/stop`)) {
          turn.stops += 1;
          turn.end();
          return new Response(JSON.stringify({ cleared: [], cancelled: true }), { status: 200, headers: { "content-type": "application/json" } });
        }
        if (!going || method !== "GET" || !url.endsWith(`${base}/turn`)) return realFetch(input, init);
        const detail = await (await realFetch(base)).json();
        if (init?.signal?.aborted) throw new DOMException("aborted", "AbortError");
        const body = new ReadableStream<Uint8Array>({
          start(controller) {
            streams.add(controller);
            // A tab that stops reading drops its connection, and the turn goes on without it.
            init?.signal?.addEventListener("abort", () => {
              if (streams.delete(controller)) controller.error(new DOMException("aborted", "AbortError"));
            });
            for (const e of [{ type: "watching", running: true, detail }, ...turn.written]) controller.enqueue(frame(e));
          },
        });
        return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
      };
    },
    { id: conversationId, writing: options.writing ?? [], stoppable: options.stoppable ?? false },
  );
  return {
    write: (...events) => page.evaluate((written) => void ((window as unknown as ServedPage).servedTurn.written = written), events),
    push: (...events) => page.evaluate((sent) => (window as unknown as ServedPage).servedTurn.push(sent), events),
    end: () => page.evaluate(() => (window as unknown as ServedPage).servedTurn.end()),
    watchers: () => page.evaluate(() => (window as unknown as ServedPage).servedTurn.watchers),
    stops: () => page.evaluate(() => (window as unknown as ServedPage).servedTurn.stops),
  };
}

export type LiveActivity = {
  /** Delivers `payloads` on the activity stream, once the page has subscribed to it. */
  emit(...payloads: StreamEvent[]): Promise<void>;
};

/** The activity stream as one the test writes to: runs start and end when the test says so. */
export async function liveActivity(page: Page): Promise<LiveActivity> {
  await page.addInitScript(() => {
    type Handler = (message: { data: string }) => void;
    let current: LiveSource | null = null;
    class LiveSource {
      onopen: (() => void) | null = null;
      onerror: (() => void) | null = null;
      readonly handlers = new Map<string, Handler[]>();
      constructor(readonly url: string) {
        current = this;
        // After the caller has set its handlers, as a real stream opens after the request.
        setTimeout(() => {
          if (current !== this) return;
          activity.open = true;
          this.onopen?.();
        }, 0);
      }
      addEventListener(name: string, handler: Handler) {
        this.handlers.set(name, [...(this.handlers.get(name) ?? []), handler]);
      }
      close() {
        if (current !== this) return;
        current = null;
        activity.open = false;
      }
    }
    const activity: Activity = {
      open: false,
      emit(payloads) {
        if (current === null) throw new Error("the page has not subscribed to the activity stream");
        for (const payload of payloads) {
          for (const handler of current.handlers.get(payload.type) ?? []) handler({ data: JSON.stringify(payload) });
        }
      },
    };
    (window as unknown as ServedPage).liveActivity = activity;
    window.EventSource = LiveSource as unknown as typeof EventSource;
  });
  return {
    emit: async (...payloads) => {
      await page.waitForFunction(() => (window as unknown as ServedPage).liveActivity.open);
      await page.evaluate((sent) => (window as unknown as ServedPage).liveActivity.emit(sent), payloads);
    },
  };
}
