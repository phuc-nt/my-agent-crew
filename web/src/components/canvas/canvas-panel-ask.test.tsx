import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import type { SendResult } from "../../lib/send-result";
import { askButton, bar, excerpt, openBox, pressSend, questionBox, typeQuestion } from "../../test/canvas-ask";
import { landed, startServer, stopServer, wait } from "../../test/canvas-hook";
import { announceSelection, find, pick, pickIn, select } from "../../test/canvas-pick";
import { editor, openPanel, saveState, typeInto } from "../../test/canvas-panel";
import type { FakeBackend } from "../../test/fake-backend";
import type { CanvasPanelProps } from "./canvas-panel";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
  vitest.setSystemTime(new Date("2026-10-02T03:05:00Z"));
});

afterEach(() => {
  stopServer();
  document.getSelection()?.removeAllRanges();
});

const TEXT = "Đoạn một\n\nĐoạn hai\n\nĐoạn ba\n";
const PASSAGE = "Đoạn hai";
/** The text with a paragraph of its own added, on line 7. */
const LONGER = `${TEXT}\nĐoạn bốn\n`;
const sent = (): CanvasPanelProps["onAsk"] => vitest.fn(async (): Promise<SendResult> => ({ status: "sent" }));
const reading = () => document.querySelector(".canvas-view") as HTMLElement;

const pickInEditor = (needle: string) => pickIn(editor() as HTMLTextAreaElement, needle);

/** One way of showing the canvas, and what a person does with the text in it. */
type Scene = {
  name: string;
  open(over?: Partial<CanvasPanelProps>): ReturnType<typeof openPanel>;
  pick(needle: string): void;
  /** Puts the caret in the text, selecting nothing. */
  collapse(): void;
  /** The cursor goes elsewhere, as it does to reach the question box. */
  leave(): void;
  /** The text becomes another, the way it does in this mode. */
  change(): Promise<void>;
  /** The button for the other mode. */
  other: string;
};

const editing: Scene = {
  name: "being edited",
  open: (over) => {
    backend.canvas.add({ title: "Ghi chú", content: TEXT });
    return openPanel({ onAsk: sent(), ...over });
  },
  pick: pickInEditor,
  collapse: () => {
    const field = editor() as HTMLTextAreaElement;
    field.setSelectionRange(0, 0);
    fireEvent.select(field);
  },
  leave: () => {
    fireEvent.blur(editor() as HTMLTextAreaElement);
  },
  change: async () => typeInto(LONGER),
  other: vi.canvas.view,
};

const viewing: Scene = {
  name: "being read",
  open: (over) => {
    backend.canvas.add({ title: "Báo cáo", agent_id: "ming", content: TEXT });
    return openPanel({ onAsk: sent(), ...over });
  },
  pick: (needle) => pick(reading(), needle),
  collapse: () => {
    const { node } = find(reading(), PASSAGE);
    select([node, 0], [node, 0]);
    announceSelection();
  },
  leave: () => {
    document.getSelection()?.removeAllRanges();
    announceSelection();
  },
  change: async () => {
    act(() => {
      backend.canvas.write("a1", LONGER, { author: "agent:ming" });
    });
    await landed();
  },
  other: vi.canvas.edit,
};

describe.each([editing, viewing])("a canvas $name", (scene) => {
  it("offers to ask about what is selected, with the lines it lies on", async () => {
    await scene.open();

    scene.pick(PASSAGE);

    expect(excerpt()).toBe(PASSAGE);
    expect(bar()).toHaveTextContent("Dòng 3 · 8 ký tự");
    expect(askButton()).toBeEnabled();
  });

  it("offers nothing before anything is selected", async () => {
    await scene.open();

    expect(bar()).toBeNull();
  });

  it("offers nothing in a panel that cannot ask, whatever is selected", async () => {
    await scene.open({ onAsk: undefined });

    scene.pick(PASSAGE);

    expect(bar()).toBeNull();
  });

  it("stops offering the passage once the person puts the caret in the text instead", async () => {
    await scene.open();
    scene.pick(PASSAGE);

    scene.collapse();

    expect(bar()).toBeNull();
  });

  it("keeps offering it when the cursor goes elsewhere", async () => {
    await scene.open();
    scene.pick(PASSAGE);

    scene.leave();

    expect(excerpt()).toBe(PASSAGE);
  });

  it("stops offering it when the text changes, and offers the next passage chosen", async () => {
    await scene.open();
    scene.pick(PASSAGE);

    await scene.change();
    expect(bar()).toBeNull();
    scene.pick("Đoạn bốn");

    expect(excerpt()).toBe("Đoạn bốn");
    expect(bar()).toHaveTextContent("Dòng 7");
  });

  it("stops offering it when the person turns to the other way of showing the canvas", async () => {
    await scene.open();
    scene.pick(PASSAGE);

    fireEvent.click(screen.getByRole("button", { name: scene.other }));

    expect(bar()).toBeNull();
  });

  it("is gone with the canvas, even for a passage chosen after", async () => {
    await scene.open();
    scene.pick(PASSAGE);
    expect(bar()).toBeInTheDocument();

    act(() => {
      backend.canvas.remove("a1");
    });
    await landed();
    expect(bar()).toBeNull();
    scene.pick(PASSAGE);

    expect(bar()).toBeNull();
  });

  it("tells why asking is off, as the chat gives it", async () => {
    await scene.open({ askDisabled: "pending" });

    scene.pick(PASSAGE);

    expect(askButton()).toBeDisabled();
    expect(screen.getByText(vi.canvas.ask.pending)).toBeInTheDocument();
  });

  it("is hidden for the history, and keeps a question begun through a look at it", async () => {
    await scene.open();
    scene.pick(PASSAGE);
    openBox();
    typeQuestion("câu hỏi dở");

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.history }));
    await landed();
    expect(bar()).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: vi.canvas.history }));

    expect(questionBox()).toHaveValue("câu hỏi dở");
    expect(excerpt()).toBe(PASSAGE);
  });

  it("does not bring back a passage that was only chosen before a look at the history", async () => {
    await scene.open();
    scene.pick(PASSAGE);

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.history }));
    await landed();
    fireEvent.click(screen.getByRole("button", { name: vi.canvas.history }));

    expect(bar()).toBeNull();
  });
});

describe("a canvas in conflict", () => {
  it("offers nothing while two versions are in conflict", async () => {
    backend.canvas.add({ title: "Ghi chú", content: TEXT });
    await openPanel({ onAsk: sent() });
    backend.canvas.onEvent = null;
    backend.canvas.write("a1", TEXT.replace("Đoạn một", "Đoạn của Ming"), { author: "agent:ming" });
    typeInto(TEXT.replace("Đoạn một", "Đoạn của tôi"));
    wait(1500);
    await landed();
    expect(saveState()).toBe("Có hai bản khác nhau");

    pickInEditor(PASSAGE);

    expect(bar()).toBeNull();
  });
});

describe("sending the question from the panel", () => {
  it("saves what was typed first and asks about the passage as of the version that holds it", async () => {
    backend.canvas.add({ title: "Ghi chú", content: TEXT });
    const { props } = await openPanel({ onAsk: sent() });
    typeInto(TEXT.replace(PASSAGE, "Đoạn hai sửa"));
    pickInEditor("Đoạn hai sửa");
    openBox();
    typeQuestion("vì sao?");

    pressSend();
    await landed();

    expect(props.onAsk).toHaveBeenCalledTimes(1);
    expect(props.onAsk).toHaveBeenCalledWith(
      { artifact_id: "a1", selection: { version: 2, text: "Đoạn hai sửa", line_start: 3, line_end: 3 } },
      "vì sao?",
    );
    expect(backend.canvas.content("a1")).toBe(TEXT.replace(PASSAGE, "Đoạn hai sửa"));
    expect(bar()).toBeNull();
  });

  it("takes the version from the dock's save, which has its time limit", async () => {
    backend.canvas.add({ title: "Ghi chú", content: TEXT });
    const flush = vitest.fn(async () => 7);
    const { props } = await openPanel({ onAsk: sent(), flush });
    pickInEditor(PASSAGE);
    openBox();
    typeQuestion("vì sao?");

    pressSend();
    await landed();

    expect(flush).toHaveBeenCalledTimes(1);
    expect(props.onAsk).toHaveBeenCalledWith(expect.objectContaining({ selection: expect.objectContaining({ version: 7 }) }), "vì sao?");
  });

  it("asks nothing when the text changed while it was being saved, and says to choose again", async () => {
    backend.canvas.add({ title: "Ghi chú", content: TEXT });
    let settle: (version: number) => void = () => {};
    const flush = vitest.fn(() => new Promise<number>((resolve) => (settle = resolve)));
    const { props } = await openPanel({ onAsk: sent(), flush });
    pickInEditor(PASSAGE);
    openBox();
    typeQuestion("vì sao?");

    pressSend();
    typeInto(TEXT.replace(PASSAGE, "Đoạn đã đổi"));
    await act(async () => settle(1));

    expect(props.onAsk).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(vi.canvas.ask.changed);
    expect(questionBox()).toHaveValue("vì sao?");
  });
});
