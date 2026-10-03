import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import type { SendResult } from "../../lib/send-result";
import { cancelButton, openBox, passage, pressSend, questionBox, setupAsk, typeQuestion } from "../../test/canvas-ask";

const REFUSAL = "Hàng chờ đã đủ";

/** The box open on `passage`, its question turned down by the server, the note of that on show. */
async function refused() {
  const made = setupAsk({
    onAsk: vitest.fn(async (): Promise<SendResult> => ({ status: "failed", error: REFUSAL })),
  });
  openBox();
  typeQuestion("vì sao?");
  pressSend();
  expect(await screen.findByRole("alert")).toHaveTextContent(REFUSAL);
  return made;
}

describe("the note of a question the server turned down", () => {
  it("stays while the very passage it was about is reported again", async () => {
    const { update } = await refused();

    update({ selection: { ...passage } });

    expect(screen.getByRole("alert")).toHaveTextContent(REFUSAL);
    expect(questionBox()).toHaveValue("vì sao?");
  });

  it.each([
    ["other words", { text: "dòng hai\ndòng tư" }],
    ["another first line", { line_start: 1 }],
    ["another last line", { line_end: 4 }],
  ])("goes once another passage is chosen: %s", async (_, change) => {
    const { update } = await refused();

    update({ selection: { ...passage, ...change } });

    expect(screen.queryByRole("alert")).toBeNull();
    expect(questionBox()).toHaveValue("vì sao?");
  });

  it("goes once the text has changed, though the words chosen are the same", async () => {
    const { update } = await refused();

    update({ selection: { ...passage }, gen: 2 });

    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("is not there when the box is opened again after being closed on it", async () => {
    await refused();

    fireEvent.click(cancelButton() as HTMLElement);
    openBox();

    expect(questionBox()).toHaveValue("");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("a passage held while the text changes", () => {
  it("is not asked about when the panel keeps handing over the passage it chose before the change", async () => {
    const { props, update } = setupAsk();
    openBox();
    typeQuestion("vì sao?");

    // The panel hands over null once the text moves; a caller that does not must not make the
    // old lines look like those of the new text.
    update({ gen: 2 });
    pressSend();

    expect(await screen.findByRole("alert")).toHaveTextContent(vi.canvas.ask.changed);
    expect(props.onAsk).not.toHaveBeenCalled();
  });
});
