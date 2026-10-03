import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import type { MessageCanvas } from "../../api/artifact-types";
import { vi } from "../../i18n/vi";
import type { SendResult } from "../../lib/send-result";
import { cancelButton, openBox, pressSend, questionBox, sendButton, setupAsk, typeQuestion } from "../../test/canvas-ask";

const ask = vi.canvas.ask;
const QUESTION = "vì sao đoạn này sai?";
type Over = NonNullable<Parameters<typeof setupAsk>[0]>;

/** A promise the test settles by hand. */
function hold<T>() {
  let settle: (value: T) => void = () => {};
  const promise = new Promise<T>((resolve) => {
    settle = resolve;
  });
  return { promise, settle };
}

const answering = (...results: SendResult[]) =>
  vitest.fn<(canvas: MessageCanvas, question: string) => Promise<SendResult>>(async () => results.shift() ?? { status: "sent" });

/** The box open on a question, ready to be sent. */
function asking(over: Over = {}) {
  const made = setupAsk(over);
  openBox();
  typeQuestion(QUESTION);
  return made;
}

describe("asking the agent about the passage", () => {
  it("saves the canvas first, then sends the passage as of the version the save gave, with the question", async () => {
    const { props } = asking();

    pressSend();

    await waitFor(() => expect(props.onAsk).toHaveBeenCalledTimes(1));
    expect(props.onAsk).toHaveBeenCalledWith(
      { artifact_id: "a1", selection: { version: 3, text: "dòng hai\ndòng ba", line_start: 2, line_end: 3 } },
      QUESTION,
    );
    expect(props.flush).toHaveBeenCalledTimes(1);
    expect(vitest.mocked(props.flush).mock.invocationCallOrder[0]).toBeLessThan(
      vitest.mocked(props.onAsk).mock.invocationCallOrder[0] ?? 0,
    );
  });

  it("sends the question without the blanks around it", async () => {
    const { props } = setupAsk();
    openBox();
    typeQuestion("  vì sao?\n");

    pressSend();

    await waitFor(() => expect(props.onAsk).toHaveBeenCalledTimes(1));
    expect(vitest.mocked(props.onAsk).mock.calls[0]?.[1]).toBe("vì sao?");
  });

  it("sends on Enter, but not on Shift+Enter, nor on the Enter that ends a word being composed", async () => {
    const { props } = asking();
    const field = questionBox() as HTMLElement;

    fireEvent.keyDown(field, { key: "Enter", shiftKey: true });
    fireEvent.keyDown(field, { key: "Enter", isComposing: true });
    fireEvent.keyDown(field, { key: "Enter", keyCode: 229 });
    expect(props.flush).not.toHaveBeenCalled();

    fireEvent.keyDown(field, { key: "Enter" });
    await waitFor(() => expect(props.onAsk).toHaveBeenCalledTimes(1));
  });

  it.each(["sent", "queued"] as const)("closes the box, and tells the panel, once the server has %s it", async (status) => {
    const { props } = asking({ onAsk: answering({ status }) });

    pressSend();

    await waitFor(() => expect(props.onAsked).toHaveBeenCalledTimes(1));
    expect(questionBox()).toBeNull();
  });

  it("keeps the box and the question, and says what went wrong, when the server turned it down; the next try starts clean", async () => {
    const second = hold<SendResult>();
    const onAsk = answering({ status: "failed", error: "Hàng chờ đã đủ" });
    const { props } = asking({ onAsk });

    pressSend();
    expect(await screen.findByRole("alert")).toHaveTextContent("Hàng chờ đã đủ");
    expect(questionBox()).toHaveValue(QUESTION);
    expect(sendButton()).toBeEnabled();
    expect(props.onAsked).not.toHaveBeenCalled();

    onAsk.mockImplementationOnce(() => second.promise);
    pressSend();
    await waitFor(() => expect(onAsk).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("alert")).toBeNull();
    await act(async () => second.settle({ status: "sent" }));

    await waitFor(() => expect(props.onAsked).toHaveBeenCalledTimes(1));
    expect(questionBox()).toBeNull();
  });

  it("asks nothing when the canvas could not be saved, says so, and keeps the question", async () => {
    const { props } = asking({ flush: vitest.fn(async () => null) });

    pressSend();

    expect(await screen.findByRole("alert")).toHaveTextContent(ask.notSaved);
    expect(props.onAsk).not.toHaveBeenCalled();
    expect(questionBox()).toHaveValue(QUESTION);
    expect(sendButton()).toBeEnabled();
  });

  it.each([
    ["the save", { flush: vitest.fn(async () => Promise.reject(new Error("no save"))) }],
    ["the send", { onAsk: vitest.fn(async () => Promise.reject(new Error("no send"))) }],
  ] as [string, Over][])("tells it in the app's own words when %s fails outright, and keeps the question", async (_, over) => {
    asking(over);

    pressSend();

    const note = await screen.findByRole("alert");
    expect(note).toHaveTextContent(vi.sendFailed.other);
    expect(note).not.toHaveTextContent(/no (save|send)/);
    expect(questionBox()).toHaveValue(QUESTION);
    expect(sendButton()).toBeEnabled();
  });

  describe("when the canvas changes while it is being saved", () => {
    async function changedDuringSave() {
      const saving = hold<number | null>();
      const made = asking({ flush: vitest.fn(() => saving.promise) });
      pressSend();
      // The panel drops a passage the text has moved under.
      made.update({ selection: null, gen: 2 });
      await act(async () => saving.settle(3));
      return made;
    }

    it("asks nothing, says to choose the passage again, and keeps the question", async () => {
      const { props } = await changedDuringSave();

      expect(screen.getByRole("alert")).toHaveTextContent(ask.changed);
      expect(props.onAsk).not.toHaveBeenCalled();
      expect(questionBox()).toHaveValue(QUESTION);
    });

    it("asks about the passage chosen again, with the question as it was, and drops the note", async () => {
      const { props, update } = await changedDuringSave();

      update({ selection: { text: "đoạn mới", line_start: 5, line_end: 5, shown: 8 } });
      expect(screen.queryByRole("alert")).toBeNull();
      pressSend();

      await waitFor(() => expect(props.onAsk).toHaveBeenCalledTimes(1));
      expect(props.onAsk).toHaveBeenCalledWith(
        { artifact_id: "a1", selection: { version: 3, text: "đoạn mới", line_start: 5, line_end: 5 } },
        QUESTION,
      );
    });
  });

  it("asks once however often it is pressed, and holds the box as it is until the save lands", async () => {
    const saving = hold<number | null>();
    const { props } = asking({ flush: vitest.fn(() => saving.promise) });

    pressSend();
    pressSend();
    fireEvent.keyDown(questionBox() as HTMLElement, { key: "Enter" });

    expect(questionBox()).toHaveAttribute("readonly");
    expect(sendButton()).toBeDisabled();
    expect(cancelButton()).toBeDisabled();
    fireEvent.keyDown(questionBox() as HTMLElement, { key: "Escape" });
    expect(questionBox()).toBeInTheDocument();
    await act(async () => saving.settle(3));

    await waitFor(() => expect(props.onAsk).toHaveBeenCalledTimes(1));
    expect(props.flush).toHaveBeenCalledTimes(1);
  });

  it("can ask a second question about another passage once the first went through", async () => {
    const { props, update } = asking();
    pressSend();
    await waitFor(() => expect(props.onAsked).toHaveBeenCalledTimes(1));

    update({ selection: { text: "đoạn khác", line_start: 9, line_end: 9, shown: 9 } });
    openBox();
    expect(questionBox()).toHaveValue("");
    typeQuestion("còn đoạn này?");
    pressSend();

    await waitFor(() => expect(props.onAsk).toHaveBeenCalledTimes(2));
    expect(props.onAsk).toHaveBeenLastCalledWith(
      { artifact_id: "a1", selection: { version: 3, text: "đoạn khác", line_start: 9, line_end: 9 } },
      "còn đoạn này?",
    );
  });
});
