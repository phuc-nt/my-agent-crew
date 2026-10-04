import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { vi } from "../../i18n/vi";
import { landed, sent, startServer, stopServer } from "../../test/canvas-hook";
import { historyShown, openHistory, rows, writes } from "../../test/canvas-history";
import { editor, openPanel, typeInto, versionLine } from "../../test/canvas-panel";
import type { FakeBackend } from "../../test/fake-backend";

const FILE = "workspace:ming/notes/tuần 1/thuc-don.md";
const REIMPORT = "POST /artifacts/a1/reimport";
const { source, reasons } = vi.canvas;

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
});

afterEach(stopServer);

const line = () => document.querySelector(".canvas-source");
const again = () => screen.getByRole("button", { name: new RegExp(`^(${source.reimport}|${source.reimporting})$`) });
/** The notices above the text, apart from the save line in the header. */
const said = (role: "alert" | "status") =>
  [...document.querySelectorAll(`.canvas-notice[role="${role}"]`)].map((notice) => notice.textContent);

/** The one notice of `role`, to read how it is drawn and where. */
const notice = (role: "alert" | "status") => document.querySelector(`.canvas-notice[role="${role}"]`);

/** a1 came from FILE, which now holds `text`; the panel is open on it. */
async function openImported(text: string | null, content = "a") {
  backend.canvas.add({ title: "Thực đơn", content, source: FILE });
  backend.canvas.files.put(FILE, text);
  return openPanel();
}

async function reimport() {
  fireEvent.click(again());
  await landed();
}

describe("where a canvas came from", () => {
  it("names the agent and the file, the folder and the name apart, with the whole path on hover", async () => {
    await openImported("a");

    expect(line()?.querySelector(".canvas-source-label")?.textContent).toBe(source.label);
    expect(line()?.querySelector(".canvas-source-dir")?.textContent).toBe("Ming/notes/tuần 1/");
    expect(line()?.querySelector(".canvas-source-file")?.textContent).toBe("thuc-don.md");
    expect(line()?.querySelector(".canvas-source-path")).toHaveAttribute("title", "Ming/notes/tuần 1/thuc-don.md");
    expect(again()).toBeEnabled();
    // A quiet button: the main actions of a canvas are the ones in its header.
    expect(again()).toHaveClass("ghost");
  });

  it("shows what the server stores of a path and nobody would see as marks, on hover too", async () => {
    // A space that is not the ordinary one, a filler, a selector, and a space at each end of a part:
    // the server refuses none of them in a path, so each can reach this line.
    backend.canvas.add({ content: "a", source: "workspace:ming/ghi chú\u{A0}/tuần\u{3164} 1 /plan\u{FE0F}.md " });
    await openPanel();

    expect(line()?.querySelector(".canvas-source-dir")?.textContent).toBe("Ming/ghi chú[U+00A0]/tuần[U+3164] 1[U+0020]/");
    expect(line()?.querySelector(".canvas-source-file")?.textContent).toBe("plan[U+FE0F].md[U+0020]");
    const whole = "Ming/ghi chú[U+00A0]/tuần[U+3164] 1[U+0020]/plan[U+FE0F].md[U+0020]";
    expect(line()?.querySelector(".canvas-source-path")).toHaveAttribute("title", whole);
  });

  it("shows a character that hides or reorders text as a mark too, should a path ever hold one", async () => {
    backend.canvas.add({ content: "a", source: "workspace:ming/a\u{202E}b/c\u{200B}d.md" });
    await openPanel();

    expect(line()?.querySelector(".canvas-source-dir")?.textContent).toBe("Ming/a[U+202E]b/");
    expect(line()?.querySelector(".canvas-source-file")?.textContent).toBe("c[U+200B]d.md");
    expect(line()?.querySelector(".canvas-source-path")).toHaveAttribute("title", "Ming/a[U+202E]b/c[U+200B]d.md");
  });

  it("links the page a canvas was taken from, in a tab that cannot reach back, and offers no re-import", async () => {
    backend.canvas.add({ content: "a", source: "https://example.com:8787/a?b=1#c" });
    await openPanel();

    // Named by the host and by where it opens; the whole address shows on hover.
    const link = screen.getByRole("link", { name: "Mở nguồn (example.com:8787) (mở trong tab mới)" });
    expect(link).toHaveAttribute("href", "https://example.com:8787/a?b=1#c");
    expect(link).toHaveAttribute("title", "https://example.com:8787/a?b=1#c");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    // The words that say where it opens are read out, and take no room on the line.
    expect(link.textContent).toBe("Mở nguồn (example.com:8787)");
    expect(link.childElementCount).toBe(0);
    expect(screen.queryByRole("button", { name: source.reimport })).toBeNull();
  });

  it("shows no line for a link that carries a login, names a host no label can hold, or leads to the app", async () => {
    const sources = [
      "https://bank.example@example.com:8787/a?b=1",
      "https://ai:matkhau@example.com/a",
      "http://good.example).evil.test/",
      `${window.location.origin}/api/artifacts/a1/render`,
    ];
    for (const { id, source: from } of sources.map((from) => backend.canvas.add({ content: "a", source: from }))) {
      const view = await openPanel({ artifactId: id });
      expect(editor()?.value, from).toBe("a");
      expect(line(), from).toBeNull();
      expect(document.querySelector(".canvas-dock a, a[target]"), from).toBeNull();
      expect(document.body.innerHTML, from).not.toContain("matkhau");
      view.unmount();
    }
  });

  it("shows nothing for a source that is neither, and links no script", async () => {
    const sources = ["", "user", "javascript:alert(1)", "data:text/html,<p>x</p>"];
    for (const { id, source: from } of sources.map((from) => backend.canvas.add({ content: "a", source: from }))) {
      const view = await openPanel({ artifactId: id });
      expect(editor()?.value, from).toBe("a");
      expect(line(), from).toBeNull();
      expect(screen.queryByRole("link", { name: /^Mở nguồn/ }), from).toBeNull();
      expect(document.querySelector('a[href^="javascript:"], a[href^="data:"]'), from).toBeNull();
      view.unmount();
    }
  });
});

describe("reading a canvas's file again", () => {
  it("saves the typing first, then asks on the version that holds it, and shows the file's text after one read", async () => {
    await openImported("từ tệp");
    typeInto("a!");

    await reimport();

    expect(writes(backend)).toEqual([
      { method: "PUT", path: "/artifacts/a1", body: { content: "a!", base_version: 1 } },
      { method: "POST", path: "/artifacts/a1/reimport", body: { base_version: 2 } },
    ]);
    expect(sent(backend, "GET")).toHaveLength(2);
    expect(editor()?.value).toBe("từ tệp");
    expect(versionLine()).toMatch(/^v3 · bạn · /);
    expect(said("status")).toEqual([source.changed(3)]);
    expect(said("status")).toEqual(["Đã nhập lại thành v3. Bản trước ở Lịch sử."]);
    expect(said("alert")).toEqual([]);
    // Said as news, right under the line that names the file.
    expect(notice("status")).toHaveClass("info");
    expect(line()?.nextElementSibling).toBe(notice("status"));

    await openHistory();
    expect(rows()[0]).toMatch(new RegExp(`^v3 · bạn · .*${vi.canvas.importedNote}$`));
  });

  it("shows the version the file became on the reply alone, when the stream says nothing of it", async () => {
    await openImported("từ tệp");
    backend.canvas.onEvent = null;

    await reimport();

    expect(sent(backend, "GET")).toHaveLength(2);
    expect(editor()?.value).toBe("từ tệp");
    expect(versionLine()).toMatch(/^v2 · bạn · /);
  });

  it("asks the server for nothing while the typing cannot be saved, and says so", async () => {
    await openImported("từ tệp");
    typeInto("a!");
    backend.canvas.refuseNext("PUT", 422);

    await reimport();

    expect(writes(backend).map((write) => write.method)).toEqual(["PUT"]);
    expect(said("alert")).toContain(source.unsaved);
    expect(editor()?.value).toBe("a!");
    expect(again()).toBeEnabled();
  });

  it("says the file holds what the canvas does, and reads nothing again", async () => {
    await openImported("a");

    await reimport();

    expect(writes(backend)).toEqual([{ method: "POST", path: "/artifacts/a1/reimport", body: { base_version: 1 } }]);
    expect(said("status")).toEqual([source.unchanged]);
    expect(sent(backend, "GET")).toHaveLength(1);
    expect(versionLine()).toMatch(/^v1 · /);
  });

  it("reads a version saved unheard that holds what the file does, so what it calls the same is what shows", async () => {
    await openImported("của agent");
    backend.canvas.onEvent = null;
    backend.canvas.write("a1", "của agent");

    await reimport();

    expect(writes(backend)).toEqual([{ method: "POST", path: "/artifacts/a1/reimport", body: { base_version: 1 } }]);
    expect(said("status")).toEqual([source.unchanged]);
    expect(said("alert")).toEqual([]);
    expect(sent(backend, "GET")).toHaveLength(2);
    expect(editor()?.value).toBe("của agent");
    expect(versionLine()).toMatch(/^v2 · /);
  });

  it("is locked while the file is read, and forgets what it said last", async () => {
    await openImported("a");
    await reimport();
    const release = backend.canvas.holdNext(REIMPORT, "request");

    fireEvent.click(again());
    await landed();
    expect(again()).toBeDisabled();
    expect(again().textContent).toBe(source.reimporting);
    expect(said("status")).toEqual([]);

    await act(release);
    await landed();
    expect(again()).toBeEnabled();
    expect(again().textContent).toBe(source.reimport);
    expect(said("status")).toEqual([source.unchanged]);
  });

  it("says in its own words why the server would not read the file, never in the server's", async () => {
    const refusals: [number, string][] = [
      [403, "Tệp nằm ngoài thư mục làm việc của agent."],
      [410, "Không còn tệp nguồn hoặc agent."],
      [413, "Tệp nguồn vượt trần cỡ của loại canvas này."],
      [422, "Tệp nguồn không hợp với loại canvas này."],
    ];
    await openImported("từ tệp");
    for (const [status, sentence] of refusals) {
      backend.canvas.refuseNext(REIMPORT, status, "refused: /Users/ming/secret.md");

      await reimport();

      expect(said("alert"), String(status)).toEqual([sentence]);
      expect(said("status"), String(status)).toEqual([]);
      expect(notice("alert"), String(status)).toHaveClass("error");
    }
    expect(editor()?.value).toBe("a");
    // None of them is a version saved meanwhile: the canvas is not read again.
    expect(sent(backend, "GET")).toHaveLength(1);
  });

  it("says a file is too large whether the server answers with a sentence or with sizes", async () => {
    await openImported("x".repeat(40));
    backend.canvas.sizeCap = 32;
    await reimport();
    expect(said("alert")).toEqual([source.tooLarge]);

    backend.canvas.sizeCap = null;
    backend.canvas.refuseNext(REIMPORT, 413);
    await reimport();
    expect(said("alert")).toEqual([source.tooLarge]);
  });

  it("says the file is gone when the server no longer finds it", async () => {
    await openImported(null);

    await reimport();

    expect(said("alert")).toEqual([source.missing]);
    expect(historyShown()).toBe(false);
  });

  it("reads the canvas again when a version was saved meanwhile, and shows none of what the refusal carried", async () => {
    await openImported("từ tệp");
    backend.canvas.onEvent = null;
    backend.canvas.write("a1", "của agent");

    await reimport();

    expect(said("alert")).toEqual([source.failed(reasons.conflict)]);
    expect(sent(backend, "GET")).toHaveLength(2);
    expect(editor()?.value).toBe("của agent");
    expect(versionLine()).toMatch(/^v2 · /);
  });

  it("takes a canvas deleted meanwhile for the deletion, and locks the button", async () => {
    await openImported("từ tệp");
    backend.canvas.onEvent = null;
    backend.canvas.remove("a1");

    await reimport();

    expect(said("alert")).toEqual([`${vi.canvas.gone} ${vi.canvas.goneHint}`]);
    expect(again()).toBeDisabled();
    expect(again().textContent).toBe(source.reimport);
  });

  it("says why in the app's words for any other refusal and for a lost connection", async () => {
    await openImported("a");
    backend.canvas.refuseNext(REIMPORT, 500);
    await reimport();
    expect(said("alert")).toEqual([source.failed(reasons.server)]);
    expect(said("alert")).toEqual(["Không nhập lại được: máy chủ không phản hồi"]);

    backend.canvas.refuseNext(REIMPORT, 507);
    await reimport();
    expect(said("alert")).toEqual([source.failed(reasons.full)]);

    backend.canvas.loseNext(REIMPORT);
    await reimport();
    expect(said("alert")).toEqual([source.failed(reasons.offline)]);
    expect(sent(backend, "GET")).toHaveLength(1);
  });
});
