import { describe, expect, it } from "vitest";
import type { ArtifactEvent } from "../api/artifact-types";
import { FakeBackend, FakeEventSource } from "./fake-backend";
import { FakeCanvas, type FakeReply } from "./fake-canvas";

const none = new URLSearchParams();

type Plain = Exclude<FakeReply, "lost">;

/** A reply that was neither lost nor held. */
function plain(result: FakeReply | Promise<FakeReply> | null): Plain {
  if (result === null || result === "lost" || result instanceof Promise) {
    throw new Error(`not a plain reply: ${String(result)}`);
  }
  return result;
}

const call = (canvas: FakeCanvas, path: string, method = "GET", body: unknown = null, params = none) =>
  plain(canvas.route(path, method, body, params));

const save = (canvas: FakeCanvas, id: string, content: string, base: unknown) =>
  call(canvas, `/artifacts/${id}`, "PUT", { content, base_version: base });

const ids = (reply: Plain) => (reply.body as { id: string }[]).map((c) => c.id);

describe("FakeCanvas versions", () => {
  it("numbers each save after the head and answers a save from an older base with the head", () => {
    const canvas = new FakeCanvas();
    canvas.add({ id: "a1", content: "một" });
    expect(save(canvas, "a1", "hai", 1)).toMatchObject({
      status: 200,
      body: { artifact_id: "a1", version: 2, author: "user", size: 3, note: "" },
    });
    expect(save(canvas, "a1", "ba", 1)).toEqual({
      status: 409,
      body: { detail: { head_version: 2, content: "hai", author: "user" } },
    });
    expect(canvas.content("a1")).toBe("hai");
  });

  it("seeds the gaps and the versions gone that folding leaves", () => {
    const canvas = new FakeCanvas();
    canvas.add({ id: "a1", content: "v3", version: 3 });
    canvas.write("a1", "v5", { author: "agent:ming", gap: 1 });
    const versions = () => (call(canvas, "/artifacts/a1/versions").body as { version: number }[]).map((v) => v.version);
    expect(versions()).toEqual([5, 3]);
    expect(call(canvas, "/artifacts/a1/versions/4")).toEqual({ status: 404, body: { detail: { head_version: 5 } } });
    canvas.forget("a1", 3);
    expect(versions()).toEqual([5]);
    expect(() => canvas.forget("a1", 5)).toThrow();
    expect(call(canvas, "/artifacts/a1").body).toMatchObject({ head_version: 5, head_author: "agent:ming", content: "v5" });
  });

  it("restores an old version as the newest and notes which one it brought back", () => {
    const canvas = new FakeCanvas();
    canvas.add({ id: "a1", content: "một" });
    save(canvas, "a1", "hai", 1);
    expect(call(canvas, "/artifacts/a1/restore", "POST", { version: 1 })).toMatchObject({
      status: 200,
      body: { version: 3, note: "restore:1", author: "user" },
    });
    expect(canvas.content("a1")).toBe("một");
    expect(call(canvas, "/artifacts/a1/restore", "POST", { version: 9 })).toEqual({
      status: 404,
      body: { detail: { head_version: 3 } },
    });
    expect(Array.isArray((call(canvas, "/artifacts/a1/restore", "POST", { version: "1" }).body as { detail: unknown }).detail)).toBe(true);
  });

  it("gives the raw text of the newest version or of an older one", () => {
    const canvas = new FakeCanvas();
    canvas.add({ id: "a1", content: "<p>một</p>" });
    save(canvas, "a1", "hai", 1);
    expect(call(canvas, "/artifacts/a1/raw")).toEqual({ status: 200, text: "hai" });
    expect(call(canvas, "/artifacts/a1/raw", "GET", null, new URLSearchParams("version=1"))).toEqual({ status: 200, text: "<p>một</p>" });
    expect(call(canvas, "/artifacts/a1/raw", "GET", null, new URLSearchParams("version=7")).status).toBe(404);
  });
});

describe("FakeCanvas checks", () => {
  it("checks a save the way the store does: the canvas, the body, the base, the size, then the room", () => {
    const canvas = new FakeCanvas();
    expect(save(canvas, "a9", "x", 1)).toEqual({ status: 404, body: { detail: "artifact not found" } });
    canvas.add({ id: "a1", title: "Một", content: "abc" });
    for (const base of [0, "1", 1.5, true]) {
      expect(Array.isArray((save(canvas, "a1", "x", base).body as { detail: unknown }).detail)).toBe(true);
    }
    expect(save(canvas, "a1", "a\r\nb\rc", 1)).toMatchObject({ status: 200, body: { size: 5 } });
    expect(canvas.content("a1")).toBe("a\nb\nc");
    canvas.sizeCap = 4;
    expect(save(canvas, "a1", "12345", 2)).toEqual({ status: 413, body: { detail: { size: 5, cap: 4 } } });
  });

  it("refuses a write past the store's room with the largest canvases, biggest first", () => {
    const canvas = new FakeCanvas();
    canvas.add({ id: "a3", title: "Ba", content: "333333" });
    canvas.add({ id: "a1", title: "Một", content: "111" });
    canvas.write("a1", "111");
    canvas.add({ id: "a2", title: "Hai", content: "2222222222" });
    canvas.add({ id: "a4", title: "Bốn", content: "4" });
    canvas.storageCap = 23;
    expect(save(canvas, "a4", "44", 1)).toEqual({
      status: 507,
      body: {
        detail: {
          used: 23,
          cap: 23,
          largest: [
            { id: "a2", title: "Hai", size: 10 },
            { id: "a1", title: "Một", size: 6 },
            { id: "a3", title: "Ba", size: 6 },
          ],
        },
      },
    });
  });

  it("refuses a bad kind, a blank title or an unknown conversation, as the routes do", () => {
    const canvas = new FakeCanvas();
    canvas.conversationExists = (id) => id === "c1";
    const create = (body: object) => call(canvas, "/artifacts", "POST", body);
    expect(Array.isArray((create({ title: "x", kind: "html" }).body as { detail: unknown }).detail)).toBe(true);
    expect(create({ title: " \n\t ", kind: "markdown" })).toEqual({ status: 422, body: { detail: "a canvas needs a title" } });
    expect(create({ title: "x", kind: "markdown", conversation_id: "c9" })).toEqual({
      status: 404,
      body: { detail: "conversation not found" },
    });
    const made = create({ title: "  Hai\ndòng​ ", kind: "code", conversation_id: "c1" });
    expect(made).toMatchObject({ status: 201, body: { title: "Hai dòng", kind: "code", content: "" } });
    const id = (made.body as { id: string }).id;
    expect(call(canvas, `/artifacts/${id}`, "PATCH", { title: "x".repeat(201) })).toEqual({
      status: 422,
      body: { detail: "a title of 201 characters is over 200" },
    });
  });

  it("answers paths and methods the routes do not have the way the router does", () => {
    const canvas = new FakeCanvas();
    canvas.add({ id: "a1" });
    expect(canvas.route("/conversations", "GET", null, none)).toBeNull();
    expect(call(canvas, "/artifacts/a1/nope")).toEqual({ status: 404, body: { detail: "Not Found" } });
    expect(call(canvas, "/artifacts", "DELETE")).toEqual({ status: 405, body: { detail: "Method Not Allowed" } });
    expect(call(canvas, "/artifacts/a1/versions", "POST")).toEqual({ status: 405, body: { detail: "Method Not Allowed" } });
  });
});

describe("FakeCanvas lists", () => {
  it("lists newest first, by conversation, by a title folded like the server's, and up to a limit", () => {
    const canvas = new FakeCanvas();
    canvas.add({ id: "a1", title: "Kế hoạch tuần", conversationIds: ["c1"] });
    canvas.add({ id: "a2", title: "Ghi chú", conversationIds: ["c2"] });
    canvas.add({ id: "a3", title: "KE HOACH tháng", conversationIds: ["c1"] });
    canvas.write("a1", "mới");
    const list = (query: string) => ids(call(canvas, "/artifacts", "GET", null, new URLSearchParams(query)));
    expect(list("")).toEqual(["a1", "a3", "a2"]);
    expect(list("conversation_id=c1")).toEqual(["a1", "a3"]);
    expect(list("q=+k%E1%BA%BF+ho%E1%BA%A1ch+")).toEqual(["a1", "a3"]);
    expect(list("limit=1")).toEqual(["a1"]);
    expect(list("conversation_id=nope")).toEqual([]);
  });

  it("puts the canvas made later first when two changed in the same second", () => {
    const canvas = new FakeCanvas();
    canvas.add({ id: "early", updated_at: "2026-10-02T09:00:00+00:00" });
    canvas.add({ id: "late", updated_at: "2026-10-02T09:00:00+00:00" });
    expect(ids(call(canvas, "/artifacts"))).toEqual(["late", "early"]);
  });
});

describe("FakeCanvas faults", () => {
  it("answers the next request it was told to refuse, then goes back to work", () => {
    const canvas = new FakeCanvas();
    canvas.add({ id: "a1", content: "x" });
    canvas.refuseNext("PUT", 409);
    expect(save(canvas, "a1", "y", 1)).toEqual({ status: 409, body: { detail: { head_version: 1, content: "x", author: "user" } } });
    canvas.refuseNext("PUT", 503);
    expect(save(canvas, "a1", "y", 1)).toEqual({ status: 503, text: "Service Unavailable" });
    canvas.refuseNext("PUT", 413);
    expect(save(canvas, "a1", "yy", 1)).toEqual({ status: 413, body: { detail: { size: 2, cap: 512 * 1024 } } });
    canvas.refuseNext("PATCH", 422, "a canvas needs a title");
    expect(call(canvas, "/artifacts/a1", "PATCH", { title: "Mới" })).toEqual({ status: 422, body: { detail: "a canvas needs a title" } });
    expect(save(canvas, "a1", "y", 1)).toMatchObject({ status: 200, body: { version: 2 } });
  });

  it("refuses only the path it was aimed at", () => {
    const canvas = new FakeCanvas();
    canvas.add({ id: "a1" });
    canvas.refuseNext("GET /artifacts/a1", 404);
    expect(call(canvas, "/artifacts").status).toBe(200);
    expect(call(canvas, "/artifacts/a1")).toEqual({ status: 404, body: { detail: "artifact not found" } });
    expect(call(canvas, "/artifacts/a1").status).toBe(200);
  });

  it("does the work of a lost request, of a held one at release, and of a held reply at once", async () => {
    const canvas = new FakeCanvas();
    canvas.add({ id: "a1", content: "x" });
    canvas.loseNext("PUT");
    expect(canvas.route("/artifacts/a1", "PUT", { content: "y", base_version: 1 }, none)).toBe("lost");
    expect(canvas.content("a1")).toBe("y");

    const releaseRequest = canvas.holdNext("PUT");
    const request = canvas.route("/artifacts/a1", "PUT", { content: "z", base_version: 2 }, none);
    expect(canvas.content("a1")).toBe("y");
    await releaseRequest();
    expect(canvas.content("a1")).toBe("z");
    await expect(request).resolves.toMatchObject({ status: 200, body: { version: 3 } });

    const releaseReply = canvas.holdNext("PUT", "reply");
    const reply = canvas.route("/artifacts/a1", "PUT", { content: "w", base_version: 3 }, none) as Promise<FakeReply>;
    expect(canvas.content("a1")).toBe("w");
    let answered = false;
    void reply.then(() => (answered = true));
    await Promise.resolve();
    expect(answered).toBe(false);
    await releaseReply();
    await expect(reply).resolves.toMatchObject({ status: 200, body: { version: 4 } });
  });
});

describe("FakeCanvas events", () => {
  it("announces each committed change with the conversations linked then, and never its text", () => {
    const canvas = new FakeCanvas();
    const events: ArtifactEvent[] = [];
    canvas.onEvent = (event) => events.push(event);
    const made = call(canvas, "/artifacts", "POST", { title: "Kế hoạch", kind: "markdown", content: "a", conversation_id: "c1" });
    expect(made).toMatchObject({
      status: 201,
      body: { head_version: 1, head_author: "user", content: "a", agent_id: "", conversation_ids: ["c1"] },
    });
    const id = (made.body as { id: string }).id;
    save(canvas, id, "b", 1);
    call(canvas, `/artifacts/${id}`, "PATCH", { title: "Mới" });
    expect(call(canvas, `/artifacts/${id}`, "DELETE")).toEqual({ status: 204 });
    expect(events.map((e) => ["deleted" in e.artifact ? "deleted" : e.artifact.head_version, e.conversation_ids])).toEqual([
      [1, []],
      [2, ["c1"]],
      [2, ["c1"]],
      ["deleted", ["c1"]],
    ]);
    expect(events[2].artifact).toMatchObject({ title: "Mới" });
    expect(JSON.stringify(events)).not.toContain('"content"');
    expect(call(canvas, `/artifacts/${id}`)).toEqual({ status: 404, body: { detail: "artifact not found" } });
  });

  it("announces the server-side writes and deletes a test makes", () => {
    const canvas = new FakeCanvas();
    canvas.add({ id: "a1", conversationIds: ["c1"] });
    const events: ArtifactEvent[] = [];
    canvas.onEvent = (event) => events.push(event);
    canvas.write("a1", "từ agent", { author: "agent:ming" });
    canvas.remove("a1");
    expect(events).toEqual([
      { type: "artifact", artifact: expect.objectContaining({ id: "a1", head_version: 2 }), conversation_ids: ["c1"] },
      { type: "artifact", artifact: { id: "a1", deleted: true }, conversation_ids: ["c1"] },
    ]);
  });
});

describe("FakeBackend canvas fetch", () => {
  const put = (content: string, base: number, init: RequestInit = {}) => ({
    method: "PUT",
    body: JSON.stringify({ content, base_version: base }),
    ...init,
  });

  it("fails the fetch of a lost reply although the save landed", async () => {
    const backend = new FakeBackend();
    backend.canvas.add({ id: "a1" });
    backend.canvas.loseNext("PUT");
    await expect(backend.fetch("/api/artifacts/a1", put("mới", 1))).rejects.toThrow(TypeError);
    expect(backend.canvas.content("a1")).toBe("mới");
  });

  it("refuses a keepalive body that would take the bytes in flight past 64 KiB, without sending it", async () => {
    const backend = new FakeBackend();
    backend.canvas.add({ id: "a1" });
    const big = "x".repeat(40_000);
    const release = backend.canvas.holdNext("PUT");
    const first = backend.fetch("/api/artifacts/a1", put(big, 1, { keepalive: true }));
    await expect(backend.fetch("/api/artifacts/a1", put(big, 1, { keepalive: true }))).rejects.toThrow(TypeError);
    await release();
    expect((await first).status).toBe(200);
    expect((await backend.fetch("/api/artifacts/a1", put(`${big}!`, 2, { keepalive: true }))).status).toBe(200);
    await expect(backend.fetch("/api/artifacts/a1", put("y".repeat(70_000), 3, { keepalive: true }))).rejects.toThrow(TypeError);
    expect((await backend.fetch("/api/artifacts/a1", put("y".repeat(70_000), 3))).status).toBe(200);
    expect(backend.requests.filter((r) => r.method === "PUT").map((r) => r.keepalive ?? false)).toEqual([true, true, false]);
  });

  it("rejects an aborted request while the work it already started still lands", async () => {
    const backend = new FakeBackend();
    backend.canvas.add({ id: "a1" });
    const release = backend.canvas.holdNext("PUT");
    const controller = new AbortController();
    const saving = backend.fetch("/api/artifacts/a1", put("mới", 1, { signal: controller.signal }));
    controller.abort();
    await expect(saving).rejects.toMatchObject({ name: "AbortError" });
    await release();
    expect(backend.canvas.content("a1")).toBe("mới");
    await expect(backend.fetch("/api/artifacts/a1", put("sau", 2, { signal: controller.signal }))).rejects.toMatchObject({
      name: "AbortError",
    });
    expect(backend.canvas.content("a1")).toBe("mới");
  });

  it("answers text, no content and JSON the way the server does", async () => {
    const backend = new FakeBackend();
    backend.canvas.add({ id: "a1", content: "chữ" });
    const raw = await backend.fetch("/api/artifacts/a1/raw");
    expect(await raw.text()).toBe("chữ");
    backend.canvas.refuseNext("PUT", 503);
    const down = await backend.fetch("/api/artifacts/a1", put("x", 1));
    expect([down.status, down.statusText, await down.text()]).toEqual([503, "Service Unavailable", "Service Unavailable"]);
    const gone = await backend.fetch("/api/artifacts/a1", { method: "DELETE" });
    expect([gone.status, await gone.text()]).toEqual([204, ""]);
    expect(await (await backend.fetch("/api/artifacts")).json()).toEqual([]);
  });

  it("links a canvas only to a conversation the backend has, and streams its changes to open sources", async () => {
    const backend = new FakeBackend();
    const conversation = backend.create();
    const create = (conversationId: string) =>
      backend.fetch("/api/artifacts", {
        method: "POST",
        body: JSON.stringify({ title: "Kế hoạch", kind: "markdown", conversation_id: conversationId }),
      });
    expect((await create("nope")).status).toBe(404);
    FakeEventSource.instances = [];
    const open = new FakeEventSource("/api/events");
    const closed = new FakeEventSource("/api/events");
    closed.close();
    const heard: string[] = [];
    open.addEventListener("artifact", (event) => heard.push(event.data));
    closed.addEventListener("artifact", () => heard.push("closed"));
    const made = await create(conversation.id);
    expect(made.status).toBe(201);
    expect(heard).toHaveLength(1);
    expect(JSON.parse(heard[0])).toMatchObject({ type: "artifact", conversation_ids: [] });
  });
});
