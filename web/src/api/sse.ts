import type { AgentEvent } from "./types";

/** Incremental server-sent-events parser. Feed raw text chunks, get whole events back. */
export class SseParser {
  private buffer = "";

  push(chunk: string): AgentEvent[] {
    this.buffer += chunk.replace(/\r\n/g, "\n");
    const events: AgentEvent[] = [];
    let boundary = this.buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = this.buffer.slice(0, boundary);
      this.buffer = this.buffer.slice(boundary + 2);
      const event = parseBlock(block);
      if (event) events.push(event);
      boundary = this.buffer.indexOf("\n\n");
    }
    return events;
  }

  /** Anything left when the stream closes without a trailing blank line. */
  flush(): AgentEvent[] {
    const rest = this.buffer;
    this.buffer = "";
    const event = rest.trim() ? parseBlock(rest) : null;
    return event ? [event] : [];
  }
}

function parseBlock(block: string): AgentEvent | null {
  const data = block
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n");
  if (!data) return null;
  try {
    const parsed = JSON.parse(data) as AgentEvent;
    return typeof parsed === "object" && parsed && "type" in parsed ? parsed : null;
  } catch {
    return null;
  }
}

/** Reads a streaming fetch body and yields every event as it arrives. */
export async function readSse(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: AgentEvent) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  const parser = new SseParser();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    for (const event of parser.push(decoder.decode(value, { stream: true }))) onEvent(event);
  }
  for (const event of parser.push(decoder.decode())) onEvent(event);
  for (const event of parser.flush()) onEvent(event);
}
