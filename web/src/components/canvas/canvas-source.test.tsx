import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import { emitArtifactEvent } from "../../lib/artifact-events";
import { SAVE_DELAY_MS } from "../../lib/canvas-runner";
import { landed, sent, startServer, stopServer, wait } from "../../test/canvas-hook";
import { historyShown, openHistory, rows, writes } from "../../test/canvas-history";
import { editor, openPanel, typeInto, versionLine } from "../../test/canvas-panel";
import type { FakeBackend } from "../../test/fake-backend";

const FILE = "workspace:ming/notes/tuần 1/thuc-don.md";
const REIMPORT = "POST /artifacts/a1/reimport";
const READ = "GET /artifacts/a1";
const { source } = vi.canvas;

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

/** The place the line says its news in, mounted with the line whether or not it has any. */
const place = () => document.querySelector('.canvas-source + [role="status"]');

/**
 * Whether the button is held off. It never takes the browser's own lock: a button locked while it
 * holds the keyboard drops the keyboard onto the page.
 */
function heldOff(): boolean {
  expect(again()).not.toHaveAttribute("disabled");
  return again().getAttribute("aria-disabled") === "true";
}

/** The stream's word of a1, as it is on the server now. */
function told(): void {
  const summary = backend.canvas.canvases.get("a1")?.summary;
  if (!summary) throw new Error("a1 is not on the server");
  act(() => emitArtifactEvent({ type: "artifact", artifact: { ...summary }, conversation_ids: [] }));
}

/**
 * `AbortSignal.timeout` on the test's clock. The real one counts on a clock no test can move, and
 * ends as this one does: the signal aborts with a `TimeoutError`.
 */
function deadlineOnTestClock() {
  return vitest.spyOn(AbortSignal, "timeout").mockImplementation((ms) => {
    const deadline = new AbortController();
    setTimeout(() => deadline.abort(new DOMException("The operation timed out.", "TimeoutError")), ms);
    return deadline.signal;
  });
}

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
    expect(heldOff()).toBe(false);
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
    expect(rows()[0]).toMatch(/^v3 · bạn · .*Nhập từ tệp$/);
  });

  it("shows the version the file became on the reply alone, when the stream says nothing of it", async () => {
    await openImported("từ tệp");
    backend.canvas.onEvent = null;

    await reimport();

    expect(sent(backend, "GET")).toHaveLength(2);
    expect(editor()?.value).toBe("từ tệp");
    expect(versionLine()).toMatch(/^v2 · bạn · /);
    expect(said("status")).toEqual(["Đã nhập lại thành v2. Bản trước ở Lịch sử."]);

    // The stream's word of that same version, come late, takes nothing back.
    told();
    await landed();
    expect(said("status")).toEqual(["Đã nhập lại thành v2. Bản trước ở Lịch sử."]);
    expect(sent(backend, "GET")).toHaveLength(2);
  });

  it("asks the server for nothing while the typing cannot be saved, and says so", async () => {
    await openImported("từ tệp");
    typeInto("a!");
    backend.canvas.refuseNext("PUT", 422);

    await reimport();

    expect(writes(backend).map((write) => write.method)).toEqual(["PUT"]);
    expect(said("alert")).toContain("Chưa lưu được bản đang sửa nên chưa nhập lại.");
    expect(editor()?.value).toBe("a!");
    expect(heldOff()).toBe(false);
  });

  it("says the typing is not saved when the save met a version written meanwhile, beside the choice that version asks for", async () => {
    await openImported("từ tệp");
    backend.canvas.onEvent = null;
    backend.canvas.write("a1", "của agent");
    typeInto("a!");

    await reimport();

    expect(writes(backend).map((write) => write.method)).toEqual(["PUT"]);
    expect(screen.getByRole("button", { name: vi.canvas.loadTheirs })).toBeInTheDocument();
    expect(said("alert")).toContain("Chưa lưu được bản đang sửa nên chưa nhập lại.");
    expect(editor()?.value).toBe("a!");
  });

  it("says the file holds what the canvas does, and reads nothing again", async () => {
    await openImported("a");

    await reimport();

    expect(writes(backend)).toEqual([{ method: "POST", path: "/artifacts/a1/reimport", body: { base_version: 1 } }]);
    expect(said("status")).toEqual(["Tệp nguồn không đổi."]);
    expect(sent(backend, "GET")).toHaveLength(1);
    expect(versionLine()).toMatch(/^v1 · /);
  });

  it("reads a version saved unheard that holds what the file does, so what it calls the same is what shows", async () => {
    await openImported("của agent");
    backend.canvas.onEvent = null;
    backend.canvas.write("a1", "của agent");

    await reimport();

    expect(writes(backend)).toEqual([{ method: "POST", path: "/artifacts/a1/reimport", body: { base_version: 1 } }]);
    expect(said("status")).toEqual(["Tệp nguồn không đổi."]);
    expect(said("alert")).toEqual([]);
    expect(sent(backend, "GET")).toHaveLength(2);
    expect(editor()?.value).toBe("của agent");
    expect(versionLine()).toMatch(/^v2 · /);
  });

  it("is held off while the file is read, takes no second press, and forgets what it said last", async () => {
    await openImported("a");
    await reimport();
    const release = backend.canvas.holdNext(REIMPORT, "request");

    fireEvent.click(again());
    await landed();
    expect(heldOff()).toBe(true);
    expect(again().textContent).toBe("Đang nhập…");
    expect(said("status")).toEqual([]);

    // A press while it is held off is not a second request.
    fireEvent.click(again());
    await landed();
    expect(writes(backend)).toHaveLength(2);

    await act(release);
    await landed();
    expect(heldOff()).toBe(false);
    expect(again().textContent).toBe("Nhập lại");
    expect(said("status")).toEqual(["Tệp nguồn không đổi."]);
    expect(writes(backend)).toHaveLength(2);
  });

  it("is held off until the canvas has been read, and a press before then asks for nothing", async () => {
    backend.canvas.add({ title: "Thực đơn", content: "a", source: FILE });
    backend.canvas.files.put(FILE, "từ tệp");
    const release = backend.canvas.holdNext(READ, "request");
    await openPanel();
    // The stream names the canvas before its first read lands: the line is drawn from that.
    told();
    expect(line()?.querySelector(".canvas-source-file")?.textContent).toBe("thuc-don.md");

    expect(heldOff()).toBe(true);
    await reimport();
    expect(writes(backend)).toEqual([]);
    expect(said("alert")).toEqual([]);
    expect(again().textContent).toBe("Nhập lại");

    await act(release);
    await landed();
    expect(heldOff()).toBe(false);
    await reimport();
    expect(writes(backend)).toEqual([{ method: "POST", path: "/artifacts/a1/reimport", body: { base_version: 1 } }]);
    expect(editor()?.value).toBe("từ tệp");
  });

  it("stays held off on a canvas whose first read failed, which stands on no version to ask on", async () => {
    backend.canvas.add({ title: "Thực đơn", content: "a", source: FILE });
    backend.canvas.files.put(FILE, "từ tệp");
    backend.canvas.refuseNext(READ, 500);
    await openPanel();
    told();

    expect(heldOff()).toBe(true);
    // The panel says the read failed; the press adds no sentence of its own to that.
    const before = said("alert");
    await reimport();

    expect(writes(backend)).toEqual([]);
    expect(said("status")).toEqual([]);
    expect(said("alert")).toEqual(before);
    expect(document.body.textContent).not.toContain("nhập lại");
    expect(again().textContent).toBe("Nhập lại");
  });

  it("gives a read that never answers thirty seconds, then says so and offers the button again", async () => {
    const deadline = deadlineOnTestClock();
    await openImported("từ tệp");
    backend.canvas.holdNext(REIMPORT, "request");

    await reimport();
    expect(deadline.mock.calls).toEqual([[30_000]]);
    wait(29_999);
    await landed();
    expect(again().textContent).toBe("Đang nhập…");
    expect(heldOff()).toBe(true);
    expect(said("alert")).toEqual([]);

    wait(1);
    await landed();
    expect(again().textContent).toBe("Nhập lại");
    expect(heldOff()).toBe(false);
    expect(said("alert")).toEqual(["Không nhập lại được: máy chủ không phản hồi"]);
    expect(editor()?.value).toBe("a");
    expect(sent(backend, "GET")).toHaveLength(1);
  });

  it("cuts no read that answers in time, however long after the deadline was set", async () => {
    deadlineOnTestClock();
    await openImported("từ tệp");

    await reimport();
    wait(30_000);
    await landed();

    expect(said("status")).toEqual(["Đã nhập lại thành v2. Bản trước ở Lịch sử."]);
    expect(said("alert")).toEqual([]);
    expect(editor()?.value).toBe("từ tệp");
  });

  it("says its news in a place that was there before it had any, and an error apart from it", async () => {
    await openImported("a");
    const there = place();
    expect(there).not.toBeNull();
    expect(line()?.nextElementSibling).toBe(there);
    // Nothing is drawn while it has nothing to say.
    expect(there?.textContent).toBe("");
    expect(there?.childNodes).toHaveLength(0);
    expect(there).not.toHaveClass("notice");

    await reimport();
    expect(place()).toBe(there);
    expect(there?.textContent).toBe("Tệp nguồn không đổi.");
    expect(there).toHaveClass("notice", "info", "canvas-notice");

    backend.canvas.refuseNext(REIMPORT, 500);
    await reimport();
    expect(place()).toBe(there);
    expect(there?.textContent).toBe("");
    expect(there).not.toHaveClass("notice");
    expect(said("alert")).toEqual(["Không nhập lại được: máy chủ không phản hồi"]);
    expect(notice("alert")).not.toBe(there);
  });

  it("says in its own words why the server would not read the file, never in the server's", async () => {
    const refusals: [number, string][] = [
      [403, "Tệp nằm ngoài thư mục làm việc của agent."],
      [410, "Không còn tệp nguồn hoặc agent."],
      [413, "Tệp nguồn vượt trần cỡ của loại canvas này."],
      // One sentence for a file that cannot be read, is no plain file, or is not what the kind holds.
      [422, "Tệp nguồn không đọc được, không phải tệp thường, hoặc không hợp với loại canvas này."],
    ];
    await openImported("từ tệp");
    for (const [status, sentence] of refusals) {
      backend.canvas.refuseNext(REIMPORT, status, "refused: /Users/ming/secret.md");

      await reimport();

      expect(said("alert"), String(status)).toEqual([sentence]);
      expect(said("status"), String(status)).toEqual([]);
      expect(notice("alert"), String(status)).toHaveClass("error");
      expect(document.body.textContent, String(status)).not.toContain("secret.md");
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

    expect(said("alert")).toEqual(["Không còn tệp nguồn hoặc agent."]);
    expect(historyShown()).toBe(false);
  });

  it("reads the canvas again when a version was saved meanwhile, and shows none of what the refusal carried", async () => {
    await openImported("từ tệp");
    backend.canvas.onEvent = null;
    backend.canvas.write("a1", "của agent");

    await reimport();

    // Said of the version the canvas then reads: reading it takes nothing back.
    expect(said("alert")).toEqual(["Không nhập lại được: máy chủ có bản mới hơn"]);
    expect(sent(backend, "GET")).toHaveLength(2);
    expect(editor()?.value).toBe("của agent");
    expect(versionLine()).toMatch(/^v2 · /);
  });

  it("takes a canvas deleted meanwhile for the deletion, and holds the button off for good", async () => {
    await openImported("từ tệp");
    backend.canvas.onEvent = null;
    backend.canvas.remove("a1");

    await reimport();

    expect(said("alert")).toEqual([`${vi.canvas.gone} ${vi.canvas.goneHint}`]);
    expect(heldOff()).toBe(true);
    expect(again().textContent).toBe("Nhập lại");

    await reimport();
    expect(writes(backend)).toHaveLength(1);
  });

  it("says why in the app's words for any other refusal and for a lost connection", async () => {
    await openImported("a");
    backend.canvas.refuseNext(REIMPORT, 500);
    await reimport();
    expect(said("alert")).toEqual(["Không nhập lại được: máy chủ không phản hồi"]);

    backend.canvas.refuseNext(REIMPORT, 507);
    await reimport();
    expect(said("alert")).toEqual(["Không nhập lại được: hết chỗ lưu canvas trên máy chủ"]);

    backend.canvas.loseNext(REIMPORT);
    await reimport();
    expect(said("alert")).toEqual(["Không nhập lại được: mất kết nối"]);
    expect(sent(backend, "GET")).toHaveLength(1);
  });
});

describe("what a re-import said, once the canvas has a newer version", () => {
  it("is taken back when an agent writes over the version the file became", async () => {
    await openImported("từ tệp");
    await reimport();
    expect(said("status")).toEqual(["Đã nhập lại thành v2. Bản trước ở Lịch sử."]);

    act(() => void backend.canvas.write("a1", "của agent", { author: "agent:ming" }));
    await landed();

    expect(versionLine()).toMatch(/^v3 · Ming · /);
    expect(said("status")).toEqual([]);
    expect(place()?.textContent).toBe("");
  });

  it("is taken back when the person's own save makes one", async () => {
    await openImported("a");
    await reimport();
    expect(said("status")).toEqual(["Tệp nguồn không đổi."]);

    typeInto("a!");
    expect(said("status")).toEqual(["Tệp nguồn không đổi."]);
    wait(SAVE_DELAY_MS);
    await landed();

    expect(versionLine()).toMatch(/^v2 · bạn · /);
    expect(said("status")).toEqual([]);
  });

  it("is taken back when it was a refusal, the same as news", async () => {
    await openImported("từ tệp");
    backend.canvas.refuseNext(REIMPORT, 403);
    await reimport();
    expect(said("alert")).toEqual(["Tệp nằm ngoài thư mục làm việc của agent."]);

    act(() => void backend.canvas.write("a1", "của agent", { author: "agent:ming" }));
    await landed();

    expect(said("alert")).toEqual([]);
  });

  it("stands when a refusal follows a save of the typing, for that version is the one it was said on", async () => {
    await openImported("từ tệp");
    typeInto("a!");
    backend.canvas.refuseNext(REIMPORT, 403);

    await reimport();

    expect(versionLine()).toMatch(/^v2 · bạn · /);
    expect(said("alert")).toEqual(["Tệp nằm ngoài thư mục làm việc của agent."]);
  });

  it("is taken back by a version newer than the one a conflict told of, not by that one", async () => {
    await openImported("từ tệp");
    backend.canvas.onEvent = null;
    backend.canvas.write("a1", "của agent");
    await reimport();
    expect(versionLine()).toMatch(/^v2 · /);
    expect(said("alert")).toEqual(["Không nhập lại được: máy chủ có bản mới hơn"]);

    backend.canvas.write("a1", "của agent, lần nữa");
    told();
    await landed();

    expect(versionLine()).toMatch(/^v3 · /);
    expect(said("alert")).toEqual([]);
  });

  it("is said again by the next press, on the version the canvas has by then", async () => {
    await openImported("a");
    await reimport();
    act(() => void backend.canvas.write("a1", "của agent", { author: "agent:ming" }));
    await landed();
    expect(said("status")).toEqual([]);

    backend.canvas.files.put(FILE, "của agent");
    await reimport();

    expect(said("status")).toEqual(["Tệp nguồn không đổi."]);
  });
});
