import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import type { FrameError } from "../../lib/frame-messages";
import { CanvasImage } from "./canvas-image";

const fetchMock = vitest.fn<typeof fetch>();

beforeEach(() => {
  vitest.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
  vitest.unstubAllGlobals();
});

const SRC = "/api/artifacts/a1/raw?version=3";

type Options = { kind?: string; version?: number; connected?: boolean };

function setup(first: Options = {}) {
  const onMount = vitest.fn<(version: number) => void>();
  const onError = vitest.fn<(error: FrameError) => void>();
  const onReread = vitest.fn<() => void>();
  const element = (now: Options) => (
    <CanvasImage
      artifactId="a1"
      title="Ảnh chụp"
      kind={now.kind ?? "image"}
      version={now.version ?? 3}
      connected={now.connected ?? true}
      onMount={onMount}
      onError={onError}
      onReread={onReread}
    />
  );
  const view = render(element(first));
  // What a rerender does not name stays as it was at the start.
  return { ...view, onMount, onError, onReread, show: (now: Options) => view.rerender(element({ ...first, ...now })) };
}

/** What the server says to a request for the picture, with the body the component must let go of. */
function answer(status: number) {
  const cancel = vitest.fn<() => Promise<void>>(async () => undefined);
  const response = { status, ok: status >= 200 && status < 300, body: { cancel } } as unknown as Response;
  return { response, cancel };
}

/** A promise that settles when the test says so, to leave a request out for a while. */
function held<T>() {
  let settle: (value: T) => void = () => {};
  const promise = new Promise<T>((resolve) => {
    settle = resolve;
  });
  return { promise, resolve: settle };
}

const picture = (container: HTMLElement) => container.querySelector("img") as HTMLImageElement;

/** The picture fails to load, and the check that follows runs to its end. */
async function fail(container: HTMLElement) {
  await act(async () => {
    fireEvent.error(picture(container));
  });
}

const note = () => screen.getByRole("status");

describe("a picture of a canvas", () => {
  it("is the image of the version it was given, under the canvas's title, and puts that version up", () => {
    const { container, onMount } = setup({ version: 3 });

    expect(picture(container).getAttribute("src")).toBe(SRC);
    expect(picture(container).getAttribute("alt")).toBe("Ảnh chụp");
    expect(picture(container).className).toBe("canvas-picture");
    expect(onMount.mock.calls).toEqual([[3]]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("is set apart as a drawing when the canvas is an SVG", () => {
    const { container } = setup({ kind: "svg" });

    expect(picture(container).className).toBe("canvas-picture vector");
  });

  it("puts each new version up once, and draws it from its own address", () => {
    const { container, onMount, show } = setup({ version: 3 });

    show({ version: 3 });
    show({ version: 4 });

    expect(onMount.mock.calls).toEqual([[3], [4]]);
    expect(picture(container).getAttribute("src")).toBe("/api/artifacts/a1/raw?version=4");
  });
});

describe("a picture that does not load", () => {
  it("is told as broken when the address answers, since what it holds is then no picture", async () => {
    const { response, cancel } = answer(200);
    fetchMock.mockResolvedValue(response);
    const { container, onError, onReread } = setup({ kind: "image" });

    await fail(container);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(SRC);
    expect(cancel).toHaveBeenCalledTimes(1);
    expect(note().textContent).toBe(vi.canvas.page.imageBroken);
    expect(note().className).toBe("notice canvas-picture-note");
    expect(container.querySelector("img")).toBeNull();
    expect(onReread).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
  });

  it("gives the agent a drawing the server holds that does not draw, once", async () => {
    fetchMock.mockResolvedValue(answer(200).response);
    const { container, onError } = setup({ kind: "svg" });

    await fail(container);

    expect(note().textContent).toBe(vi.canvas.page.imageBroken);
    expect(onError.mock.calls).toEqual([[{ message: vi.canvas.page.svgInvalid, source: "", line: 0, column: 0 }]]);
  });

  it("reads the canvas again when its version is gone, and blames no drawing for that", async () => {
    const { response, cancel } = answer(404);
    fetchMock.mockResolvedValue(response);
    const { container, onError, onReread } = setup({ kind: "svg" });

    await fail(container);

    expect(onReread).toHaveBeenCalledTimes(1);
    expect(cancel).toHaveBeenCalledTimes(1);
    expect(onError).not.toHaveBeenCalled();
    expect(note().textContent).toBe(vi.canvas.page.imageBroken);
  });

  it("blames neither the picture nor the version for a server that is failing", async () => {
    fetchMock.mockResolvedValue(answer(500).response);
    const { container, onError, onReread } = setup({ kind: "svg" });

    await fail(container);

    expect(note().textContent).toBe(vi.canvas.page.imageBroken);
    expect(onReread).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
  });

  it("waits for the network when the address does not answer, and says nothing to the agent", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const { container, onError, onReread } = setup({ kind: "svg" });

    await fail(container);

    expect(note().textContent).toBe(vi.canvas.page.imageWaiting);
    expect(note().className).toBe("muted canvas-picture-note");
    expect(container.querySelector("img")).toBeNull();
    expect(onReread).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
  });

  it("draws it again when the live stream comes back after a drop, and not while the stream is down", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const { container, show } = setup({ connected: true });
    await fail(container);

    show({ connected: false });

    expect(note().textContent).toBe(vi.canvas.page.imageWaiting);

    show({ connected: true });

    expect(screen.queryByRole("status")).toBeNull();
    expect(picture(container).getAttribute("src")).toBe(SRC);
  });

  it("leaves a picture that is showing alone when the stream drops and comes back", () => {
    const { container, show } = setup({ connected: true });
    const before = picture(container);

    show({ connected: false });
    show({ connected: true });

    expect(picture(container)).toBe(before);
  });

  it("does not try a broken picture again when the stream comes back, since the network was not the cause", async () => {
    fetchMock.mockResolvedValue(answer(200).response);
    const { container, show } = setup({ connected: true });
    await fail(container);

    show({ connected: false });
    show({ connected: true });

    expect(note().textContent).toBe(vi.canvas.page.imageBroken);
    expect(container.querySelector("img")).toBeNull();
  });

  it("lets the newest check decide when two are out, and the older one's late answer changes nothing", async () => {
    const first = held<Response>();
    fetchMock.mockReturnValueOnce(first.promise).mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const { container, onError } = setup({ kind: "svg" });
    const img = picture(container);

    await act(async () => {
      fireEvent.error(img);
      fireEvent.error(img);
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(note().textContent).toBe(vi.canvas.page.imageWaiting);

    await act(async () => first.resolve(answer(200).response));

    expect(note().textContent).toBe(vi.canvas.page.imageWaiting);
    expect(onError).not.toHaveBeenCalled();
  });

  it("drops a check that is still out when the picture goes away", async () => {
    const pending = held<Response>();
    fetchMock.mockReturnValueOnce(pending.promise);
    const { container, onError, unmount } = setup({ kind: "svg" });
    await fail(container);

    unmount();
    await act(async () => pending.resolve(answer(200).response));

    expect(onError).not.toHaveBeenCalled();
  });
});
