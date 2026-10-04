import { act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ArtifactSummary } from "../api/artifact-types";
import { emitArtifactEvent } from "../lib/artifact-events";
import { landed, openCanvas, sent, startServer, stopServer } from "../test/canvas-hook";
import type { FakeBackend } from "../test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
});

afterEach(stopServer);

/** The file is read into a1 again as its next version, with the stream saying nothing of it. */
function reimportUnheard(text: string): ArtifactSummary {
  backend.canvas.onEvent = null;
  backend.canvas.write("a1", text, { author: "user" });
  return { ...backend.canvas.canvases.get("a1")!.summary };
}

describe("a canvas told what a re-import left", () => {
  it("reads the new version, as it would on the stream's word of it", async () => {
    backend.canvas.add({ content: "a" });
    const { result } = await openCanvas();
    const summary = reimportUnheard("a\nb");

    act(() => result.current.imported(summary));
    expect(sent(backend, "GET")).toHaveLength(2);
    await landed();

    expect(result.current.state.text).toBe("a\nb");
    expect(result.current.state.base.version).toBe(2);
    expect(result.current.status).toBe("saved");
  });

  it("says a change is waiting when that read fails, not that all is saved", async () => {
    backend.canvas.add({ content: "a" });
    const { result } = await openCanvas();
    const summary = reimportUnheard("a\nb");
    backend.canvas.refuseNext("GET", 500);

    act(() => result.current.imported(summary));
    await landed();

    expect(result.current.state.text).toBe("a");
    expect(result.current.status).toBe("newer");
  });

  it("reads once when the stream tells of the version first and the reply second", async () => {
    backend.canvas.add({ content: "a" });
    const { result } = await openCanvas();

    act(() => {
      backend.canvas.write("a1", "a\nb", { author: "user" });
    });
    act(() => result.current.imported({ ...backend.canvas.canvases.get("a1")!.summary }));
    await landed();

    expect(sent(backend, "GET")).toHaveLength(2);
    expect(result.current.state.text).toBe("a\nb");
    expect(result.current.status).toBe("saved");
  });

  it("reads once when the reply tells of the version first and the stream second", async () => {
    backend.canvas.add({ content: "a" });
    const { result } = await openCanvas();
    const summary = reimportUnheard("a\nb");
    const release = backend.canvas.holdNext("GET", "request");

    act(() => result.current.imported(summary));
    act(() => emitArtifactEvent({ type: "artifact", artifact: summary, conversation_ids: [] }));
    await act(release);
    await landed();

    expect(sent(backend, "GET")).toHaveLength(2);
    expect(result.current.state.text).toBe("a\nb");
    expect(result.current.status).toBe("saved");
  });

  it("reads nothing more when told of a version it already shows", async () => {
    backend.canvas.add({ content: "a" });
    const { result } = await openCanvas();
    const summary = reimportUnheard("a\nb");
    act(() => result.current.imported(summary));
    await landed();

    act(() => result.current.imported(summary));
    await landed();

    expect(sent(backend, "GET")).toHaveLength(2);
    expect(result.current.status).toBe("saved");
  });

  it("keeps what the person typed meanwhile and says a change is waiting", async () => {
    backend.canvas.add({ content: "a" });
    const { result } = await openCanvas();
    const summary = reimportUnheard("a\nb");
    act(() => result.current.edit("a!"));

    act(() => result.current.imported(summary));
    await landed();

    expect(sent(backend, "GET")).toHaveLength(1);
    expect(result.current.state.text).toBe("a!");
    expect(result.current.status).toBe("newer");
  });
});
