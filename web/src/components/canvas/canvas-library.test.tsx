import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { artifactApi } from "../../api/artifact-client";
import { SEARCH_WAIT_MS } from "../../hooks/use-canvas-library";
import { vi } from "../../i18n/vi";
import { landed, setVisibility, startServer, stopServer, wait } from "../../test/canvas-hook";
import type { FakeBackend } from "../../test/fake-backend";
import type { CanvasSeed } from "../../test/fake-canvas";
import { CanvasLibrary } from "./canvas-library";

const { canvas } = vi;
const ONE = "0123456789ab";
const NAMES: Record<string, string> = { coach: "HLV", user: "Trợ lý", ghost: "Bóng​ma" };
const name = (id: string) => NAMES[id] ?? id;

let backend: FakeBackend;
/** The canvases the library asked to open, oldest first. */
let opened: string[];

beforeEach(() => {
  backend = startServer();
  opened = [];
  // The fake stamps its first canvas at 03:00:00 and each later write a second on.
  vitest.setSystemTime(new Date("2026-10-02T03:10:00Z"));
});

afterEach(stopServer);

/** The library over `seeds`, the last of them the newest, once its first read is in. */
async function show(...seeds: CanvasSeed[]) {
  for (const seed of seeds) backend.canvas.add(seed);
  render(<CanvasLibrary connected agentName={name} onOpen={(id) => opened.push(id)} />);
  await landed();
}

const library = () => screen.getByTestId("canvas-library");
const rows = () => screen.queryAllByTestId("canvas-library-row");
const rowOf = (title: string) => screen.getByText(title).closest<HTMLElement>("[data-testid=canvas-library-row]")!;
const sourceOf = (title: string) => rowOf(title).querySelector(".canvas-library-source")?.textContent ?? null;
const box = () => screen.getByRole("searchbox", { name: canvas.librarySearch });
const deletes = () => backend.requests.filter((r) => r.method === "DELETE").map((r) => r.path);

async function type(words: string) {
  fireEvent.change(box(), { target: { value: words } });
  wait(SEARCH_WAIT_MS);
  await landed();
}

describe("a row of the library", () => {
  it("says the canvas's kind, its version, who made it and when, and what all its versions hold", async () => {
    await show({ title: "Kế hoạch", content: "abc", agent_id: "coach", version: 3 });

    const [row] = rows();
    expect(within(row).getByText("Kế hoạch")).toHaveClass("canvas-library-title");
    expect(within(row).getByText(canvas.kinds.markdown)).toHaveClass("badge");
    expect(row).toHaveTextContent(`v3 · ${canvas.libraryCreatedBy} HLV · ${vi.time.minutes(10)}`);
    expect(row).toHaveTextContent(`3 B ${canvas.libraryAllVersions}`);
  });

  it("opens the canvas whose name is clicked, one with no name too, and deletes nothing by it", async () => {
    vitest.spyOn(window, "confirm").mockReturnValue(true);
    await show({ id: ONE, title: "Kế hoạch" }, { id: "ba9876543210", title: "" });

    fireEvent.click(screen.getByRole("button", { name: "Kế hoạch" }));
    expect(opened).toEqual([ONE]);
    fireEvent.click(screen.getByRole("button", { name: canvas.untitled }));

    expect(opened).toEqual([ONE, "ba9876543210"]);
    expect(deletes()).toEqual([]);
    expect(rows()).toHaveLength(2);
  });

  it("names each of the six kinds, a code canvas with its language, and any other kind as the server does", async () => {
    await show(
      ...["markdown", "html", "svg", "mermaid", "sheet"].map((kind) => ({ title: kind, kind })),
      { title: "picture", kind: "image", content: null },
      { title: "script", kind: "code", language: "python" },
      { title: "plain", kind: "code" },
    );

    const badges = rows().map((row) => row.querySelector(".badge")?.textContent);
    const { kinds } = canvas;
    expect(badges).toEqual([kinds.code, `${kinds.code} · python`, kinds.image, "sheet", kinds.mermaid, kinds.svg, kinds.html, kinds.markdown]);
  });

  // The server keeps a language for a canvas of any kind; it means something for code alone.
  it("says a language of a code canvas only, whatever one the server keeps for another kind", async () => {
    await show({ title: "note", kind: "markdown", language: "python" });

    expect(rows()[0].querySelector(".badge")?.textContent).toBe(canvas.kinds.markdown);
  });

  it("says when a canvas was last written, not when it was made", async () => {
    await show({ title: "Sửa gần đây", created_at: "2026-09-30T03:10:00Z" });

    expect(rowOf("Sửa gần đây")).toHaveTextContent(`· ${vi.time.minutes(10)}`);
  });

  // An agent's name is its profile's wording, shown here beside what the agent itself wrote.
  it("writes out what nobody would see in the name of the agent that made a canvas", async () => {
    await show({ title: "Của agent lạ", agent_id: "ghost" });

    expect(rowOf("Của agent lạ")).toHaveTextContent(`${canvas.libraryCreatedBy} Bóng[U+200B]ma ·`);
  });

  it("calls the person who made a canvas \"bạn\" and an agent by its name, even one whose id is user", async () => {
    await show({ title: "Của người" }, { title: "Của agent", agent_id: "coach" }, { title: "Của agent user", agent_id: "user" });

    expect(rowOf("Của người")).toHaveTextContent(`${canvas.libraryCreatedBy} ${canvas.you} ·`);
    expect(rowOf("Của agent")).toHaveTextContent(`${canvas.libraryCreatedBy} HLV ·`);
    expect(rowOf("Của agent user")).toHaveTextContent(`${canvas.libraryCreatedBy} Trợ lý ·`);
  });

  // A title is the agent's wording: it is drawn as text, with what would hide in it written out.
  it("draws a title as text, marks a character nobody would see in it, and names a canvas that has none", async () => {
    await show({ title: "a‮b" }, { title: "" }, { title: "<img src=x onerror=alert(1)>" });

    expect(screen.getByText("a[U+202E]b")).toBeInTheDocument();
    expect(screen.getByText(canvas.untitled)).toBeInTheDocument();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(library().querySelector("img")).toBeNull();
  });

  it("says where a canvas came from: a workspace file by agent and path, a page by the host the agent gave", async () => {
    await show(
      { title: "Tệp", source: "workspace:coach/notes/plan‮.md " },
      { title: "Tệp của agent lạ", source: "workspace:ghost/a.md" },
      { title: "Trang", source: "https://example.com/a/b?c=1" },
      { title: "Lạ", source: "javascript:alert(1)" },
      { title: "Có đăng nhập", source: "https://user:pw@example.com/" },
      { title: "Làm ở đây" },
    );

    expect(sourceOf("Tệp")).toBe("HLV/notes/plan[U+202E].md[U+0020]");
    expect(sourceOf("Tệp của agent lạ")).toBe("Bóng[U+200B]ma/a.md");
    expect(sourceOf("Trang")).toBe(canvas.librarySourceDeclared("example.com"));
    expect(sourceOf("Lạ")).toBeNull();
    expect(sourceOf("Có đăng nhập")).toBeNull();
    expect(sourceOf("Làm ở đây")).toBeNull();
    // The library says where a canvas came from; it leads nowhere.
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("leaves the size out of a row the count does not name, and shows one of nothing as a size", async () => {
    const count = { count: 2, bytes: 0, cap: 100, by_artifact: { a1: 0 } };
    vitest.spyOn(artifactApi, "usage").mockResolvedValue(count);
    await show({ title: "Rỗng" }, { title: "Chưa đếm", content: "abc" });

    expect(rowOf("Rỗng")).toHaveTextContent(`0 B ${canvas.libraryAllVersions}`);
    expect(rowOf("Chưa đếm")).not.toHaveTextContent(canvas.libraryAllVersions);
    expect(library()).not.toHaveTextContent("NaN");
  });
});

describe("the head of the library", () => {
  it("says how many canvases there are and what they hold of the room they share", async () => {
    await show({ content: "a".repeat(2048) }, { content: "abc" });

    expect(library().querySelector(".canvas-library-total")).toHaveTextContent(canvas.libraryTotal(2, "2 KB", "1 GB"));
  });

  it("counts every canvas in the total, however few a search shows", async () => {
    await show({ title: "Kế hoạch tuần", content: "abc" }, { title: "Ghi chú", content: "de" });

    await type("kế");

    expect(rows()).toHaveLength(1);
    expect(library().querySelector(".canvas-library-total")).toHaveTextContent(canvas.libraryTotal(2, "5 B", "1 GB"));
  });

  it("shows the canvases with no sizes and no total when what they hold could not be read", async () => {
    backend.canvas.refuseNext("GET /artifacts/usage", 503);
    await show({ title: "Một", content: "abc" });

    expect(rows()).toHaveLength(1);
    expect(library()).not.toHaveTextContent("NaN");
    expect(library()).not.toHaveTextContent(canvas.libraryAllVersions);
    expect(library().querySelector(".canvas-library-total")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("finds canvases by name a while after the last key, and says when none has that name", async () => {
    await show({ title: "Kế hoạch tuần" }, { title: "Ghi chú" });
    expect(box()).toHaveAttribute("maxlength", "200");
    expect(box()).toHaveAttribute("placeholder", canvas.librarySearch);

    await type("kế");
    expect(box()).toHaveValue("kế");
    expect(rows()).toHaveLength(1);
    expect(rows()[0]).toHaveTextContent("Kế hoạch tuần");

    await type("không có");
    expect(rows()).toHaveLength(0);
    expect(screen.getByText(canvas.libraryNoMatch)).toBeInTheDocument();
    expect(screen.queryByText(canvas.libraryEmpty)).toBeNull();
  });
});

describe("the states of the library", () => {
  it("says it is loading until the first read is in", async () => {
    const release = backend.canvas.holdNext("GET /artifacts", "request");
    await show({ title: "Một" });

    expect(screen.getByText(canvas.libraryLoading)).toBeInTheDocument();
    expect(screen.queryByText(canvas.libraryEmpty)).toBeNull();
    expect(rows()).toHaveLength(0);

    await act(() => release());
    await landed();
    expect(screen.queryByText(canvas.libraryLoading)).toBeNull();
    expect(rows()).toHaveLength(1);
  });

  it("says the canvases could not be read, and reads them again on the button", async () => {
    backend.canvas.refuseNext("GET /artifacts", 503);
    await show({ title: "Một" });

    const notice = screen.getByRole("alert");
    expect(notice).toHaveTextContent(canvas.libraryFailed);
    expect(screen.queryByText(canvas.libraryLoading)).toBeNull();
    expect(screen.queryByText(canvas.libraryEmpty)).toBeNull();

    fireEvent.click(within(notice).getByRole("button", { name: canvas.retry }));
    await landed();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(rows()).toHaveLength(1);
  });

  it("keeps the canvases it has under the notice when reading them again fails", async () => {
    await show({ title: "Một" });
    backend.canvas.refuseNext("GET /artifacts", 503);

    setVisibility("visible");
    await landed();

    expect(screen.getByRole("alert")).toHaveTextContent(canvas.libraryFailed);
    expect(rows()).toHaveLength(1);
  });

  it("says how a first canvas comes to be when there is none, rather than that none matches", async () => {
    await show();

    expect(screen.getByText(canvas.libraryEmpty)).toBeInTheDocument();
    expect(screen.queryByText(canvas.libraryNoMatch)).toBeNull();
    expect(library().querySelector(".canvas-library-total")).toHaveTextContent(canvas.libraryTotal(0, "0 B", "1 GB"));
  });

  // The server lists two hundred at the most: past that, the oldest are found by name.
  it("says the list is only the newest when there are more canvases than it shows, unless a name is searched", async () => {
    await show(...Array.from({ length: 201 }, (_, n) => ({ title: `Canvas ${n}` })));

    expect(rows()).toHaveLength(200);
    expect(screen.getByText(canvas.libraryCapped(200))).toBeInTheDocument();

    await type("canvas 20");
    expect(rows()).toHaveLength(2);
    expect(screen.queryByText(canvas.libraryCapped(2))).toBeNull();
  });

  it("says nothing of older canvases when it shows every one", async () => {
    await show({ title: "Một" }, { title: "Hai" });

    expect(library()).not.toHaveTextContent(canvas.libraryCapped(2));
  });
});

describe("deleting from the library", () => {
  it("asks first, deletes nothing when the person says no, and drops the row when they say yes", async () => {
    const confirm = vitest.spyOn(window, "confirm").mockReturnValue(false);
    await show({ id: ONE, title: "Một" });
    const button = screen.getByRole("button", { name: canvas.deleteLabel("Một") });

    fireEvent.click(button);
    await landed();
    expect(confirm.mock.calls).toEqual([[canvas.deleteConfirm("Một")]]);
    expect(deletes()).toEqual([]);
    expect(rows()).toHaveLength(1);

    confirm.mockReturnValue(true);
    fireEvent.click(button);
    await landed();
    expect(deletes()).toEqual([`/artifacts/${ONE}`]);
    expect(rows()).toHaveLength(0);
  });

  it("names the canvas in the question as the row shows it", async () => {
    const confirm = vitest.spyOn(window, "confirm").mockReturnValue(false);
    await show({ title: "" }, { title: "a‮b" });

    fireEvent.click(screen.getByRole("button", { name: canvas.deleteLabel("a[U+202E]b") }));
    fireEvent.click(screen.getByRole("button", { name: canvas.deleteLabel(canvas.untitled) }));

    expect(confirm.mock.calls).toEqual([[canvas.deleteConfirm("a[U+202E]b")], [canvas.deleteConfirm(canvas.untitled)]]);
  });

  it("says under the row that the server would not delete it, and keeps the row", async () => {
    vitest.spyOn(window, "confirm").mockReturnValue(true);
    await show({ id: ONE, title: "Một" }, { title: "Hai" });
    backend.canvas.refuseNext("DELETE", 503);

    fireEvent.click(screen.getByRole("button", { name: canvas.deleteLabel("Một") }));
    await landed();

    expect(within(rowOf("Một")).getByRole("alert")).toHaveTextContent(canvas.deleteFailed);
    expect(within(rowOf("Hai")).queryByRole("alert")).toBeNull();
    expect(rows()).toHaveLength(2);
  });
});

describe("once a canvas is deleted from the library", () => {
  beforeEach(() => {
    vitest.spyOn(window, "confirm").mockReturnValue(true);
  });

  const nameOf = (title: string) => screen.getByRole("button", { name: title });
  const deleteOf = (title: string) => screen.getByRole("button", { name: canvas.deleteLabel(title) });
  const said = () => screen.getByRole("status").textContent;

  /** The person has the keyboard on a row's delete button, presses it and says yes. */
  async function remove(title: string) {
    const button = deleteOf(title);
    act(() => button.focus());
    fireEvent.click(button);
    await landed();
  }

  it("puts the keyboard on the name of the row after it, and says which canvas is gone", async () => {
    await show({ title: "Một" }, { title: "Hai" }, { title: "Ba" });
    expect(said()).toBe("");

    await remove("Hai");

    expect(rows()).toHaveLength(2);
    expect(nameOf("Một")).toHaveFocus();
    expect(said()).toBe(canvas.libraryDeleted("Hai"));
  });

  it("puts the keyboard on the name of the row before it when it was the last", async () => {
    await show({ title: "Một" }, { title: "Hai" }, { title: "Ba" });

    await remove("Một");

    expect(nameOf("Hai")).toHaveFocus();
    expect(said()).toBe(canvas.libraryDeleted("Một"));
  });

  it("puts the keyboard in the search box when no canvas is left", async () => {
    await show({ title: "Một" });

    await remove("Một");

    expect(rows()).toHaveLength(0);
    expect(box()).toHaveFocus();
    expect(said()).toBe(canvas.libraryDeleted("Một"));
  });

  it("does as much for a canvas the server no longer has", async () => {
    await show({ title: "Một" }, { title: "Hai" }, { title: "Ba" });
    backend.canvas.refuseNext("DELETE", 404);

    await remove("Ba");

    expect(rows()).toHaveLength(2);
    expect(nameOf("Hai")).toHaveFocus();
    expect(said()).toBe(canvas.libraryDeleted("Ba"));
  });

  it("leaves the keyboard on the button and says nothing when the server would not delete it", async () => {
    await show({ title: "Một" }, { title: "Hai" });
    backend.canvas.refuseNext("DELETE", 503);

    await remove("Hai");

    expect(rows()).toHaveLength(2);
    expect(deleteOf("Hai")).toHaveFocus();
    expect(said()).toBe("");
    expect(within(rowOf("Hai")).getByRole("alert")).toHaveTextContent(canvas.deleteFailed);
  });

  it("stops saying one canvas is gone as soon as the next delete is asked for", async () => {
    await show({ title: "Một" }, { title: "Hai" }, { title: "Ba" });
    await remove("Ba");
    expect(said()).toBe(canvas.libraryDeleted("Ba"));
    backend.canvas.refuseNext("DELETE", 503);

    await remove("Hai");

    expect(said()).toBe("");
    expect(deleteOf("Hai")).toHaveFocus();
  });

  it("names the canvas that is gone as its row did, one with no name too", async () => {
    await show({ title: "" }, { title: "a‮b" });

    await remove("a[U+202E]b");
    expect(said()).toBe(canvas.libraryDeleted("a[U+202E]b"));
    await remove(canvas.untitled);

    expect(said()).toBe(canvas.libraryDeleted(canvas.untitled));
  });

  it("leaves the keyboard where the person took it while the server was answering", async () => {
    await show({ title: "Một" }, { title: "Hai" });
    const answer = backend.canvas.holdNext("DELETE", "reply");
    await remove("Hai");
    act(() => box().focus());

    await act(() => answer());
    await landed();

    expect(rows()).toHaveLength(1);
    expect(box()).toHaveFocus();
    expect(said()).toBe(canvas.libraryDeleted("Hai"));
  });
});
