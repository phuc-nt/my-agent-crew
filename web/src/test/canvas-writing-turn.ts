import { act, screen } from "@testing-library/react";
import type { AgentEvent, ToolCall } from "../api/types";
import { box, say } from "./canvas-app";
import { landed } from "./canvas-hook";
import type { FakeBackend } from "./fake-backend";

/**
 * A turn in which the agent writes a canvas, fed to the app a piece at a time: the events as the
 * server streams them, and the two things the screen makes of them.
 */

type Piece = Extract<AgentEvent, { type: "tool_call_delta" }>;

/** A piece of a canvas write the model is still writing; a new canvas unless said otherwise. */
export const piece = (chunk: string, partial: Partial<Piece> = {}): AgentEvent => ({
  type: "tool_call_delta",
  index: 0,
  name: "artifact_create",
  chunk,
  attempt: 0,
  ...partial,
});

/** The step's answer, which names the calls the pieces were of. */
export const answer = (tool_calls: ToolCall[], content = ""): AgentEvent => ({
  type: "assistant_message",
  message_id: `m-${tool_calls.map((call) => call.id).join("-")}-${content.length}`,
  content,
  tool_calls,
  provider: null,
  model: null,
  cost_usd: null,
});

export const started = (call: ToolCall): AgentEvent => ({
  type: "tool_call",
  tool_call_id: call.id,
  name: call.name,
  arguments: call.arguments,
});

export const ended = (call: ToolCall, output: string, ok = true): AgentEvent => ({
  type: "tool_result",
  tool_call_id: call.id,
  name: call.name,
  ok,
  output,
});

export const done: AgentEvent = { type: "done", spent_usd: 0, unknown_cost_calls: 0 };

/** The model gives its route up and starts the answer over, as the server says it. */
export const startOver = (attempt: number): AgentEvent[] => [
  { type: "route_fallback", provider: "p", model: "m", error: "503" },
  piece("", { name: "", attempt }),
];

export type HeldTurn = ReturnType<FakeBackend["holdTurn"]>;

/** The person sends `text` from the chat box, where their keyboard is, and the turn it starts stays open to be fed. */
export async function startTurn(backend: FakeBackend, text = "viết kế hoạch tuần"): Promise<HeldTurn> {
  const turn = backend.holdTurn("c1");
  act(() => box().focus());
  await say(text);
  return turn;
}

/** Sends `events` down the open turn together, and lets the screen draw them. */
export async function stream(turn: HeldTurn, ...events: AgentEvent[]): Promise<void> {
  act(() => turn.push(events));
  await landed();
  await landed();
}

/** The frame showing a canvas being written, when one is up. */
export const frame = () => screen.queryByTestId("canvas-writing");
/** The same, for a test that has just said it is up. */
export const shownFrame = () => screen.getByTestId("canvas-writing");
export const writingCards = () => screen.queryAllByTestId("canvas-writing-card");
/** The Canvas button, however many canvases it counts. */
export const canvasToggle = () => document.querySelector(".canvas-button") as HTMLButtonElement;
/** The panel of a canvas that is stored, when the dock holds one. */
export const panel = () => document.querySelector<HTMLElement>(".canvas-panel");
