import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { vi } from "../../i18n/vi";
import { saveInBackground } from "../../lib/canvas-handoff";
import { landed, startServer, stopServer } from "../../test/canvas-hook";
import { leftCanvas } from "../../test/canvas-left";
import type { FakeBackend } from "../../test/fake-backend";
import { CanvasSection } from "./canvas-section";

const { canvas } = vi;
const name = (id: string) => id;

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
  backend.canvas.add({ title: "Kế hoạch" });
});

afterEach(stopServer);

const lists = () => backend.requests.filter((r) => r.path.startsWith("/artifacts?")).map((r) => r.path);
const rows = () => screen.queryAllByTestId("canvas-library-row");

describe("the canvas section of the manage screen", () => {
  it("shows the library, and asks about no conversation's canvases", async () => {
    render(<CanvasSection connected agentName={name} />);
    await landed();

    expect(rows()).toHaveLength(1);
    expect(rows()[0]).toHaveTextContent("Kế hoạch");
    expect(lists()).toEqual(["/artifacts?limit=200"]);
    expect(backend.requests.some((r) => r.path.includes("conversation"))).toBe(false);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  // A canvas left for another screen hands its last save on; this is where the person may be by then.
  it("says above the library that a save left behind did not land, until the person puts the line away", async () => {
    render(<CanvasSection connected agentName={name} />);
    await landed();

    await act(() => saveInBackground(leftCanvas("a9", async () => null)));

    const notice = screen.getByRole("alert");
    expect(notice).toHaveTextContent(canvas.handoffFailed(canvas.untitled, true));
    const library = screen.getByTestId("canvas-library");
    expect(notice.compareDocumentPosition(library) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(library).not.toContainElement(notice);

    fireEvent.click(within(notice).getByRole("button", { name: canvas.dismiss }));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(rows()).toHaveLength(1);
  });

  // That a message went before its canvas was saved is said in the chat it went in, nowhere else.
  it("says nothing of a message sent before its canvas was saved", async () => {
    render(<CanvasSection connected agentName={name} />);
    await landed();
    await act(() => saveInBackground(leftCanvas("a9", async () => null)));

    expect(screen.queryByText(canvas.sentUnsaved)).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("reads the library again when the stream comes back", async () => {
    const view = render(<CanvasSection connected agentName={name} />);
    await landed();

    view.rerender(<CanvasSection connected={false} agentName={name} />);
    view.rerender(<CanvasSection connected agentName={name} />);
    await landed();

    expect(lists()).toHaveLength(2);
  });
});
