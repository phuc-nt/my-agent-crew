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
  });

  it("shows a character that hides or reorders text in the path as a mark, on hover too", async () => {
    backend.canvas.add({ content: "a", source: "workspace:ming/a\u{202E}b/c\u{200B}d.md" });
    await openPanel();

    expect(line()?.querySelector(".canvas-source-dir")?.textContent).toBe("Ming/a[U+202E]b/");
    expect(line()?.querySelector(".canvas-source-file")?.textContent).toBe("c[U+200B]d.md");
    expect(line()?.querySelector(".canvas-source-path")).toHaveAttribute("title", "Ming/a[U+202E]b/c[U+200B]d.md");
  });

  it("links the page a canvas was taken from, in a tab that cannot reach back, and offers no re-import", async () => {
    backend.canvas.add({ content: "a", source: "https://bank.example@example.com:8787/a?b=1" });
    await openPanel();

    const link = screen.getByRole("link", { name: source.open("example.com:8787") });
    expect(link).toHaveAttribute("href", "https://bank.example@example.com:8787/a?b=1");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.queryByRole("button", { name: source.reimport })).toBeNull();
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
    expect(said("alert")).toEqual([]);

    await openHistory();
    expect(rows()[0]).toMatch(new RegExp(`^v3 · bạn · .*${vi.canvas.importedNote}$`));
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
      [403, source.outside],
      [410, source.missing],
      [413, source.tooLarge],
      [422, source.unfit],
    ];
    await openImported("từ tệp");
    for (const [status, sentence] of refusals) {
      backend.canvas.refuseNext(REIMPORT, status, "refused: /Users/ming/secret.md");

      await reimport();

      expect(said("alert"), String(status)).toEqual([sentence]);
      expect(said("status"), String(status)).toEqual([]);
    }
    expect(editor()?.value).toBe("a");
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

    backend.canvas.refuseNext(REIMPORT, 507);
    await reimport();
    expect(said("alert")).toEqual([source.failed(reasons.full)]);

    backend.canvas.loseNext(REIMPORT);
    await reimport();
    expect(said("alert")).toEqual([source.failed(reasons.offline)]);
  });
});
