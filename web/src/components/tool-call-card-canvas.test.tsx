import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import type { ThreadItem, ToolStatus } from "../state/thread-reducer";
import type { CanvasLinks } from "./canvas/canvas-card";
import { MessageThread } from "./message-thread";
import { ToolCallCard } from "./tool-call-card";

const NOTE = "0123456789ab";
const WRITES = ["artifact_create", "artifact_edit", "artifact_rewrite", "artifact_import"];
const OTHER_CANVAS_TOOLS = ["artifact_read", "artifact_list"];
const SETTLED: ToolStatus[] = ["failed", "denied", "stopped", "awaiting"];

type Tool = Extract<ThreadItem, { kind: "tool" }>;

function call(name: string, status: ToolStatus, fields: Partial<Tool> = {}): Tool {
  const finished = status === "done";
  return {
    kind: "tool",
    id: `t-${name}-${status}`,
    name,
    arguments: { id: NOTE, title: "Ghi chú" },
    output: finished ? `[artifact ${NOTE} v2]\nok` : null,
    status,
    ...fields,
  };
}

function links() {
  return {
    titleOf: vitest.fn(() => "Ghi chú"),
    isGone: vitest.fn(() => false),
    verify: vitest.fn(),
    open: vitest.fn(),
  } satisfies CanvasLinks;
}

const canvasCard = () => screen.queryByTestId("canvas-card");
const plainCard = () => screen.queryByTestId("tool-card");

describe("which tool calls the thread draws as a canvas card", () => {
  it("is each canvas write while it runs and once it is done", () => {
    for (const name of WRITES) {
      for (const status of ["running", "done"] as const) {
        const view = render(<ToolCallCard item={call(name, status)} canvas={links()} />);
        expect(canvasCard(), `${name} ${status}`).not.toBeNull();
        expect(plainCard(), `${name} ${status}`).toBeNull();
        view.unmount();
      }
    }
  });

  it("is not a write that failed, was refused, was cut short or still waits to be allowed", () => {
    for (const name of WRITES) {
      for (const status of SETTLED) {
        const view = render(<ToolCallCard item={call(name, status)} canvas={links()} />);
        expect(canvasCard(), `${name} ${status}`).toBeNull();
        expect(plainCard(), `${name} ${status}`).toHaveAttribute("data-tool", name);
        view.unmount();
      }
    }
  });

  it("keeps the plain card for the canvas tools that read", () => {
    for (const name of OTHER_CANVAS_TOOLS) {
      for (const status of ["running", "done"] as const) {
        const view = render(<ToolCallCard item={call(name, status)} canvas={links()} />);
        expect(canvasCard(), `${name} ${status}`).toBeNull();
        expect(plainCard(), `${name} ${status}`).toHaveAttribute("data-tool", name);
        view.unmount();
      }
    }
  });

  it("keeps the plain card for a canvas written out to a file, which shows the canvas and the file it names", () => {
    for (const status of ["awaiting", "running", "done"] as const) {
      const item = call("artifact_export", status, { arguments: { id: NOTE, path: "out/thuc-don.md" }, output: null });
      const view = render(<ToolCallCard item={item} canvas={links()} />);
      expect(canvasCard(), status).toBeNull();
      expect(plainCard(), status).toHaveAttribute("data-tool", "artifact_export");
      expect(plainCard(), status).toHaveTextContent(`id=${NOTE}, path=out/thuc-don.md`);
      view.unmount();
    }
  });

  it("keeps the plain card for a write when the thread cannot open canvases", () => {
    for (const name of WRITES) {
      const view = render(<ToolCallCard item={call(name, "done")} />);
      expect(canvasCard(), name).toBeNull();
      expect(plainCard(), name).toHaveAttribute("data-tool", name);
      view.unmount();
    }
  });

  it("leaves a handed-off task and every other tool as they were", () => {
    render(
      <>
        <ToolCallCard item={call("delegate", "done", { arguments: { agent: "coach", task: "x" } })} canvas={links()} />
        <ToolCallCard item={call("web_search", "done")} canvas={links()} />
      </>,
    );

    expect(screen.getByTestId("delegate-card")).toBeInTheDocument();
    expect(plainCard()).toHaveAttribute("data-tool", "web_search");
    expect(canvasCard()).toBeNull();
  });

  it("shows the arguments and the output of a failed write, as the plain card always did", () => {
    render(
      <ToolCallCard
        item={call("artifact_edit", "failed", { arguments: { id: NOTE, old_text: "cũ" }, output: "old_text not found" })}
        canvas={links()}
      />,
    );

    expect(plainCard()).toHaveTextContent("old_text=cũ");
    expect(plainCard()).toHaveTextContent(vi.toolFailed);
    expect(screen.getByRole("button", { name: vi.showOutput })).toBeInTheDocument();
  });
});

describe("a canvas card in the message thread", () => {
  const user: ThreadItem = { kind: "user", id: "m1", text: "viết ghi chú" };

  function thread(items: ThreadItem[], canvas?: CanvasLinks) {
    return render(
      <MessageThread
        items={items}
        streaming={null}
        busy={false}
        onSuggestion={() => {}}
        echoOnly={false}
        agentId="master"
        canvas={canvas}
      />,
    );
  }

  it("is given the thread's links, so Open reaches the canvas the card names", () => {
    const canvas = links();
    thread([user, call("artifact_create", "done")], canvas);

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.card.openLabel("Ghi chú") }));

    expect(canvas.open).toHaveBeenCalledExactlyOnceWith(NOTE);
    expect(canvas.verify).toHaveBeenCalledExactlyOnceWith(NOTE);
  });

  it("is the plain card in a thread that was given no links", () => {
    thread([user, call("artifact_create", "done")]);

    expect(canvasCard()).toBeNull();
    expect(plainCard()).toHaveAttribute("data-tool", "artifact_create");
  });

  it("sits among the other cards of a turn in the order they happened", () => {
    thread(
      [
        user,
        call("web_search", "done", { id: "t1" }),
        call("artifact_create", "done", { id: "t2" }),
        call("artifact_read", "done", { id: "t3" }),
      ],
      links(),
    );

    const cards = screen.getAllByTestId(/^(tool-card|canvas-card)$/).map((card) => card.getAttribute("data-tool"));
    expect(cards).toEqual(["web_search", "artifact_create", "artifact_read"]);
  });
});
