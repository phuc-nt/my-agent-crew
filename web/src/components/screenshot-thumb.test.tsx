// The picture `browser_screenshot` saved is shown small where its call is shown: on the step
// of a run and on the tool card of a chat. Only that tool, only once the call went through,
// and nothing is left behind by a picture that does not load.
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { RunStep } from "../api/types";
import { agentFileUrl } from "../api/client";
import { vi } from "../i18n/vi";
import type { ThreadItem, ToolStatus } from "../state/thread-reducer";
import { fakeRun } from "../test/fake-backend";
import { Item } from "./message-item";
import { RunCard } from "./run-timeline";
import { ToolCallCard } from "./tool-call-card";

type ToolStep = Extract<RunStep, { kind: "tool" }>;
type ToolItem = Extract<ThreadItem, { kind: "tool" }>;

const PATH = "screenshots/20261013T120000Z-don.png";
const OTHER = "screenshots/20261013T120500Z-gio.jpg";
const saved = (label: string, path: string) => `Đã lưu ảnh chụp tab ${label} vào ${path}.`;
/** The tool's whole answer, as a chat card has it. */
const ANSWER = `${saved("don", PATH)}\nKích thước 1280x720, 48 KB.`;
/** A run's step keeps its output this way: whitespace collapsed, cut at 160 characters. */
const preview = (output: string) => output.replace(/\s+/g, " ").trim().slice(0, 160);

const thumb = () => screen.queryByTestId("screenshot-thumb");
const picture = () => within(screen.getByTestId("screenshot-thumb")).getByRole("img");
const before = (first: Element, second: Element) =>
  Boolean(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING);

/** What every thumbnail has to be, wherever it is drawn. */
function expectThumb(agentId: string, path: string, label: string) {
  const link = screen.getByTestId("screenshot-thumb");
  const url = agentFileUrl(agentId, path);
  expect(url).toBe(`/api/agents/${agentId}/files?path=${encodeURIComponent(path)}`);
  expect(link.tagName).toBe("A");
  expect(link).toHaveAttribute("href", url);
  expect(link).toHaveAttribute("target", "_blank");
  expect(link).toHaveAttribute("rel", "noreferrer");
  expect(picture()).toHaveAttribute("src", url);
  expect(picture()).toHaveAttribute("loading", "lazy");
  // The link is named by its picture.
  expect(screen.getByRole("link", { name: `Ảnh chụp tab ${label}` })).toBe(link);
}

describe("a screenshot on the step of a run", () => {
  const step = (over: Partial<ToolStep> = {}): ToolStep => ({
    kind: "tool",
    name: "browser_screenshot",
    tool_call_id: "tc1",
    arguments: { tab: "don" },
    ok: true,
    output: preview(ANSWER),
    duration_ms: 420,
    ...over,
  });
  const show = (shown: ToolStep, agentId = "coach") =>
    render(<RunCard run={fakeRun({ agent_id: agentId, steps: [shown] })} agentName="HLV" expanded />);

  it("is a small picture that opens the whole one in a tab of its own, from the workspace of the run's agent", () => {
    show(step());

    expectThumb("coach", PATH, "don");
    expect(screen.getAllByTestId("screenshot-thumb")).toHaveLength(1);
  });

  it("is read from a preview cut before the answer ended", () => {
    const long = preview(`${saved("don", PATH)}\n\n${"Trang dài. ".repeat(40)}`);
    expect(long).toHaveLength(160);
    show(step({ output: long }));

    expectThumb("coach", PATH, "don");
  });

  it("stands under the step's arguments and above what it answered, which still opens", async () => {
    show(step());

    const row = screen.getByTestId("run-step");
    const output = within(row).getByRole("button", { name: vi.showOutput });
    expect(before(within(row).getByText("tab=don"), screen.getByTestId("screenshot-thumb"))).toBe(true);
    expect(before(screen.getByTestId("screenshot-thumb"), output)).toBe(true);

    await userEvent.click(output);
    expect(within(row).getByText(/Đã lưu ảnh chụp tab don/)).toBeInTheDocument();
    expectThumb("coach", PATH, "don");
  });

  it("asks the workspace of whoever ran, an id with a character an address escapes included", () => {
    show(step(), "đội/1");

    expect(screen.getByTestId("screenshot-thumb")).toHaveAttribute(
      "href",
      `/api/agents/${encodeURIComponent("đội/1")}/files?path=${encodeURIComponent(PATH)}`,
    );
  });

  it.each([
    ["a call that failed", { ok: false }],
    ["a call still running", { ok: null, output: null }],
    ["a call still running that already has a line", { ok: null }],
    ["an answer that names no picture", { output: "Không chụp được: tab đã đóng." }],
    ["a step with no output", { output: null }],
    ["another tool whose answer reads the same", { name: "browser_text" }],
    ["a tool of no browser at all", { name: "read_file", arguments: { path: PATH } }],
  ] as [string, Partial<ToolStep>][])("is not there for %s", (_what, over) => {
    show(step(over));

    expect(screen.getByTestId("run-step")).toBeInTheDocument();
    expect(thumb()).not.toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("goes away when the picture does not load, and the step reads as it did before", () => {
    show(step());
    const row = screen.getByTestId("run-step");

    fireEvent.error(picture());

    expect(thumb()).not.toBeInTheDocument();
    expect(within(row).queryByRole("link")).not.toBeInTheDocument();
    expect(within(row).queryByRole("img")).not.toBeInTheDocument();
    expect(within(row).getByRole("button", { name: vi.showOutput })).toBeInTheDocument();
    expect(row).toHaveTextContent("tab=don");
    expect(row).toHaveAttribute("data-state", "done");
  });

  it("stays once it has loaded", () => {
    show(step());

    fireEvent.load(picture());

    expectThumb("coach", PATH, "don");
  });
});

describe("a screenshot on a tool card of the chat", () => {
  const item = (over: Partial<ToolItem> = {}): ToolItem => ({
    kind: "tool",
    id: "tc1",
    name: "browser_screenshot",
    arguments: { tab: "don" },
    output: ANSWER,
    status: "done",
    ...over,
  });

  it("is the same small picture, from the workspace of the conversation's agent", () => {
    render(<ToolCallCard item={item()} agentId="coach" />);

    expectThumb("coach", PATH, "don");
    expect(within(screen.getByTestId("tool-card")).getByTestId("screenshot-thumb")).toBeInTheDocument();
  });

  it("is handed the agent by the thread's item", () => {
    render(<Item item={item()} agentId="purchases" speaker="Thủ kho" />);

    expectThumb("purchases", PATH, "don");
  });

  it("names the tab the picture is of", () => {
    render(<ToolCallCard item={item({ output: saved("gio_hang-2", "out/20261013T120500Z-gio_hang-2.jpg") })} agentId="coach" />);

    expectThumb("coach", "out/20261013T120500Z-gio_hang-2.jpg", "gio_hang-2");
  });

  it.each(["running", "failed", "awaiting", "denied", "stopped"] as ToolStatus[])(
    "is not there for a call that is %s",
    (status) => {
      render(<ToolCallCard item={item({ status })} agentId="coach" />);

      expect(screen.getByTestId("tool-card")).toBeInTheDocument();
      expect(thumb()).not.toBeInTheDocument();
    },
  );

  it.each([
    ["another tool whose answer reads the same", { name: "browser_snapshot" }],
    ["a tool of no browser at all", { name: "write_file", arguments: { path: PATH } }],
    ["an answer that names no picture", { output: "Không chụp được: tab đã đóng." }],
    ["a call with no answer yet", { output: null }],
  ] as [string, Partial<ToolItem>][])("is not there for %s", (_what, over) => {
    render(<ToolCallCard item={item(over)} agentId="coach" />);

    expect(thumb()).not.toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("is not there where nobody says whose workspace the picture is in", () => {
    render(<ToolCallCard item={item()} />);

    expect(screen.getByTestId("tool-card")).toHaveTextContent("browser_screenshot");
    expect(thumb()).not.toBeInTheDocument();
  });

  it("goes away when the picture does not load, and the card keeps its output", () => {
    render(<ToolCallCard item={item()} agentId="coach" />);

    fireEvent.error(picture());

    expect(thumb()).not.toBeInTheDocument();
    const card = screen.getByTestId("tool-card");
    expect(within(card).queryByRole("link")).not.toBeInTheDocument();
    expect(within(card).getByRole("button", { name: vi.showOutput })).toBeInTheDocument();
  });

  it("tries again for a card that comes to name another picture, and not for the one that failed", () => {
    const { rerender } = render(<ToolCallCard item={item()} agentId="coach" />);
    fireEvent.error(picture());
    expect(thumb()).not.toBeInTheDocument();

    // The same answer drawn again is the same picture that did not load.
    rerender(<ToolCallCard item={item({ arguments: { tab: "don", full_page: true } })} agentId="coach" />);
    expect(thumb()).not.toBeInTheDocument();

    rerender(<ToolCallCard item={item({ output: saved("gio", OTHER) })} agentId="coach" />);
    expectThumb("coach", OTHER, "gio");
  });
});
