// The picture `computer_screenshot` saved, shown small on the step of a run and on the tool
// card of a chat. The tool says either where it saved the picture or that the screen is
// unchanged since a frame; a run's step keeps only 160 characters of that, which for an agent
// keeping its pictures deep ends before the path, so an unchanged screen is read by its frame.
// A line that reads as neither draws nothing.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { agentFileUrl } from "../api/client";
import type { RunStep } from "../api/types";
import { vi } from "../i18n/vi";
import type { ThreadItem } from "../state/thread-reducer";
import { FakeBackend, coachAgent, fakeAgent, fakeRun } from "../test/fake-backend";
import { MessageThread } from "./message-thread";
import { RunCard } from "./run-timeline";
import { ToolCallCard } from "./tool-call-card";

type ToolStep = Extract<RunStep, { kind: "tool" }>;
type ToolItem = Extract<ThreadItem, { kind: "tool" }>;

const F = "00000000000000a1-1456x910-1";
const DEEP = "records/kept/for/the/owner/by/this/agent";
const SHALLOW_PATH = `desktop/${F}.png`;
const DEEP_PATH = `${DEEP}/desktop/${F}.png`;
const SAVED = (path: string) =>
  `Đã chụp màn hình và lưu vào ${path}. frame_id: ${F} (1456×910; toạ độ của computer_act tính theo điểm ảnh của ảnh này).\nỨng dụng phía trước: Notes`;
const UNCHANGED = (path: string) =>
  `Màn hình không đổi từ lần chụp trước. frame_id: ${F} (1456×910); ảnh đã lưu ở ${path} vẫn đúng. Muốn hỏi về ảnh thì gọi lại kèm \`question\`.`;
/** What a run's step keeps of an answer (`activity/step_previews.py`). */
function preview(text: string): string {
  const flat = text.split(/\s+/).filter(Boolean).join(" ");
  return flat.length <= 160 ? flat : `${flat.slice(0, 160)}…`;
}

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  backend.agents = [fakeAgent, { ...coachAgent, computer: "on", computer_apps: [], write_paths: [DEEP] }];
  vitest.stubGlobal("fetch", backend.fetch);
});

afterEach(() => {
  vitest.unstubAllGlobals();
});

const thumbs = () => screen.queryAllByTestId("screenshot-thumb");
const hrefs = () => thumbs().map((a) => a.getAttribute("href"));
const url = (path: string) => agentFileUrl("coach", path);
const readsOfAgent = () => backend.requests.filter((r) => r.method === "GET" && r.path === "/agents/coach").length;

const step = (output: string | null, over: Partial<ToolStep> = {}): ToolStep => ({
  kind: "tool",
  name: "computer_screenshot",
  tool_call_id: `tc-${Math.random()}`,
  arguments: {},
  ok: true,
  output,
  duration_ms: 900,
  ...over,
});
const run = (...steps: ToolStep[]) => render(<RunCard run={fakeRun({ agent_id: "coach", steps })} agentName="HLV" expanded />);

const item = (output: string | null, over: Partial<ToolItem> = {}): ToolItem => ({
  kind: "tool",
  id: `tc-${Math.random()}`,
  name: "computer_screenshot",
  arguments: {},
  output,
  status: "done",
  ...over,
});

describe("a desktop screenshot on the step of a run", () => {
  it.each([
    ["the workspace's folder", SHALLOW_PATH],
    ["a deep write path", DEEP_PATH],
  ])("is the picture it saved under %s, read from the line the step keeps", (_where, path) => {
    expect(preview(SAVED(path)).length).toBeGreaterThan(160);
    run(step(preview(SAVED(path))));

    const link = screen.getByTestId("screenshot-thumb");
    expect(link).toHaveAttribute("href", url(path));
    expect(link).toHaveAttribute("target", "_blank");
    expect(within(link).getByRole("img")).toHaveAttribute("src", url(path));
    expect(within(link).getByRole("img")).toHaveAttribute("alt", vi.desktop.screenshotAlt(1456, 910));
  });

  it.each([
    ["the workspace's folder", SHALLOW_PATH],
    ["a deep write path", DEEP_PATH],
  ])("is, for an unchanged screen under %s, the picture of the same frame a step before saved", (_where, path) => {
    run(step(preview(SAVED(path))), step(preview(UNCHANGED(path))));

    expect(hrefs()).toEqual([url(path), url(path)]);
    expect(readsOfAgent()).toBe(0);
  });

  it("is, for an unchanged screen whose frame no step of the run saved, the picture in the agent's folder", async () => {
    run(step(preview(UNCHANGED(DEEP_PATH))));

    await waitFor(() => expect(hrefs()).toEqual([url(DEEP_PATH)]));
    expect(readsOfAgent()).toBe(1);
  });

  it("reads the agent's row once for the steps that look for its folder together, and again for a later look", async () => {
    const other = "00000000000000b2-1456x910-1";
    run(step(preview(UNCHANGED(DEEP_PATH))), step(preview(UNCHANGED(DEEP_PATH).replaceAll(F, other))));

    await waitFor(() => expect(hrefs()).toEqual([url(DEEP_PATH), url(`${DEEP}/desktop/${other}.png`)]));
    expect(readsOfAgent()).toBe(1);

    // Its write paths may have changed since: a look once that read is answered reads again.
    backend.agents = [fakeAgent, { ...coachAgent, computer: "on", computer_apps: [], write_paths: [] }];
    render(<ToolCallCard item={item(UNCHANGED(DEEP_PATH))} agentId="coach" />);
    await waitFor(() => expect(hrefs()).toContain(url(SHALLOW_PATH)));
    expect(readsOfAgent()).toBe(2);
  });

  it("is not taken from a step that failed", () => {
    run(step(preview(SAVED("elsewhere/desktop/" + F + ".png")), { ok: false }), step(preview(UNCHANGED(DEEP_PATH))));

    // The failed step is not a saved picture: the frame is found in the agent's folder.
    return waitFor(() => expect(hrefs()).toEqual([url(DEEP_PATH)]));
  });

  it.each([
    ["a line that reads as neither", "Màn hình của máy đang khoá, nên không chụp và không thao tác được."],
    ["a step with no output", null],
  ])("draws nothing for %s", async (_what, output) => {
    run(step(output));
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(screen.getByTestId("run-step")).toBeInTheDocument();
    expect(thumbs()).toHaveLength(0);
    expect(readsOfAgent()).toBe(0);
  });

  it("draws nothing for another tool whose answer reads the same", () => {
    run(step(preview(SAVED(SHALLOW_PATH)), { name: "computer_state" }));

    expect(thumbs()).toHaveLength(0);
  });

  it("goes away when the picture does not load, and the step reads as it did", () => {
    run(step(preview(SAVED(SHALLOW_PATH))));

    fireEvent.error(within(screen.getByTestId("screenshot-thumb")).getByRole("img"));

    expect(thumbs()).toHaveLength(0);
    expect(screen.getByTestId("run-step")).toHaveAttribute("data-state", "done");
  });
});

describe("a desktop screenshot on a tool card of the chat", () => {
  it.each([
    ["the workspace's folder", SHALLOW_PATH],
    ["a deep write path", DEEP_PATH],
  ])("is the picture it saved under %s, read from the whole answer", (_where, path) => {
    render(<ToolCallCard item={item(SAVED(path))} agentId="coach" />);

    expect(hrefs()).toEqual([url(path)]);
  });

  it.each([
    ["the workspace's folder", SHALLOW_PATH],
    ["a deep write path", DEEP_PATH],
  ])("is, for an unchanged screen under %s, the picture the thread's earlier screenshot saved", (_where, path) => {
    render(
      <MessageThread items={[item(SAVED(path)), item(UNCHANGED(path))]} streaming={null} busy={false} onSuggestion={() => {}} echoOnly={false} agentId="coach" />,
    );

    expect(hrefs()).toEqual([url(path), url(path)]);
    expect(readsOfAgent()).toBe(0);
  });

  it("is not taken from a call of the thread that failed", async () => {
    render(
      <MessageThread
        items={[item(SAVED(`elsewhere/desktop/${F}.png`), { status: "failed" }), item(UNCHANGED(DEEP_PATH))]}
        streaming={null}
        busy={false}
        onSuggestion={() => {}}
        echoOnly={false}
        agentId="coach"
      />,
    );

    // The failed call is not a saved picture: the frame is found in the agent's folder.
    await waitFor(() => expect(hrefs()).toEqual([url(DEEP_PATH)]));
  });

  it("is, for an unchanged screen the thread saved nowhere, the picture in the agent's folder", async () => {
    render(<ToolCallCard item={item(UNCHANGED(DEEP_PATH))} agentId="coach" />);

    await waitFor(() => expect(hrefs()).toEqual([url(DEEP_PATH)]));
  });

  it("draws nothing for an answer that reads as neither, or a call not done", async () => {
    render(<ToolCallCard item={item("Màn hình của máy đang tắt.")} agentId="coach" />);
    render(<ToolCallCard item={item(SAVED(SHALLOW_PATH), { status: "failed" })} agentId="coach" />);
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(screen.getAllByTestId("tool-card")).toHaveLength(2);
    expect(thumbs()).toHaveLength(0);
  });

  it("draws nothing where nobody says whose workspace the picture is in", () => {
    render(<ToolCallCard item={item(SAVED(SHALLOW_PATH))} />);

    expect(thumbs()).toHaveLength(0);
  });

  it("is left out when the folder's picture cannot be placed", async () => {
    backend.agents = [fakeAgent];
    render(<ToolCallCard item={item(UNCHANGED(DEEP_PATH))} agentId="coach" />);

    await waitFor(() => expect(readsOfAgent()).toBe(1));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(thumbs()).toHaveLength(0);
  });
});
