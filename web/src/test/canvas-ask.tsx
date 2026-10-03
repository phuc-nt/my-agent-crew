import { fireEvent, render, screen, within } from "@testing-library/react";
import { vi as vitest } from "vitest";
import { CanvasAsk } from "../components/canvas/canvas-ask";
import { vi } from "../i18n/vi";
import type { CanvasSelection } from "../lib/canvas-selection";
import type { SendResult } from "../lib/send-result";

type Props = Parameters<typeof CanvasAsk>[0];

/** Two lines of a canvas, selected as they are. */
export const passage: CanvasSelection = { text: "dòng hai\ndòng ba", line_start: 2, line_end: 3, shown: 16 };

/**
 * The ask bar on its own, the panel's save and the chat's send replaced by spies that succeed.
 * `update` is the panel drawing it again with other props.
 */
export function setupAsk(over: Partial<Props> = {}) {
  let current: Props = {
    artifactId: "a1",
    selection: passage,
    gen: 1,
    hidden: false,
    disabled: null,
    flush: vitest.fn(async (): Promise<number | null> => 3),
    onAsk: vitest.fn(async (): Promise<SendResult> => ({ status: "sent" })),
    onAsked: vitest.fn(),
    ...over,
  };
  const props = current;
  const view = render(<CanvasAsk {...current} />);
  const update = (next: Partial<Props>) => {
    current = { ...current, ...next };
    view.rerender(<CanvasAsk {...current} />);
  };
  return { ...view, props, update };
}

export const bar = () => screen.queryByRole("group", { name: vi.canvas.ask.group });
/** A control of the bar: the chat beside it has a Gửi button of its own. */
const inBar = (role: "button" | "textbox", name: string) => {
  const root = bar();
  return root ? within(root).queryByRole(role, { name }) : null;
};
export const askButton = () => inBar("button", vi.canvas.ask.button);
export const questionBox = () => inBar("textbox", vi.canvas.ask.question) as HTMLTextAreaElement | null;
export const sendButton = () => inBar("button", vi.send);
export const cancelButton = () => inBar("button", vi.canvas.ask.cancel);
/** What the bar shows of the passage, apart from the lines and the notes around it. */
export const excerpt = () => bar()?.querySelector("blockquote")?.textContent ?? null;

/** The person presses "Hỏi về đoạn này". */
export const openBox = () => fireEvent.click(askButton() as HTMLElement);
/** The person types until the question box holds `text`. */
export const typeQuestion = (text: string) => fireEvent.change(questionBox() as HTMLElement, { target: { value: text } });
/** The person presses Gửi. */
export const pressSend = () => fireEvent.click(sendButton() as HTMLElement);
