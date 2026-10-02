import { describe, expect, it } from "vitest";
import type { FocusSelection } from "../api/artifact-types";
import { FakeBackend } from "./fake-backend";
import { FakeCanvas, type FakeReply } from "./fake-canvas";

const PICK: FocusSelection = { version: 1, text: "chạy 5 km", line_start: 2, line_end: 2 };

type Plain = Exclude<FakeReply, "lost">;

function plain(result: FakeReply | Promise<FakeReply> | null): Plain {
  if (result === null || result === "lost" || result instanceof Promise) {
    throw new Error(`not a plain reply: ${String(result)}`);
  }
  return result;
}

const get = (canvas: FakeCanvas, cid = "c1") => plain(canvas.focusRoute(cid, "GET", null));
const put = (canvas: FakeCanvas, body: unknown, cid = "c1") => plain(canvas.focusRoute(cid, "PUT", body));
const refusal = (reply: FakeReply | null) => plain(reply);

/** A fake server with one conversation and a canvas "a1" of three lines. */
function server() {
  const canvas = new FakeCanvas();
  canvas.add({ id: "a1", title: "Kế hoạch", content: "tuần này\nchạy 5 km\nngủ sớm" });
  canvas.add({ id: "a2", title: "Mua sắm" });
  return canvas;
}

describe("FakeCanvas focus route", () => {
  it("reads nothing until a canvas is opened, then the canvas and its selection", () => {
    const canvas = server();
    expect(get(canvas)).toEqual({ status: 200, body: null });

    expect(put(canvas, { artifact_id: "a1", selection: PICK })).toEqual({
      status: 200,
      body: { artifact_id: "a1", selection: PICK },
    });
    expect(get(canvas).body).toEqual({ artifact_id: "a1", selection: PICK });
    // Another conversation has its own.
    expect(get(canvas, "c2").body).toBeNull();
  });

  it("shares the canvas it opens with the conversation, so the conversation's list has it", () => {
    const canvas = server();
    put(canvas, { artifact_id: "a2" });

    const listed = plain(canvas.route("/artifacts", "GET", null, new URLSearchParams({ conversation_id: "c1" })));
    expect((listed.body as { id: string }[]).map((c) => c.id)).toEqual(["a2"]);
  });

  it("closes on a null canvas and answers null", () => {
    const canvas = server();
    put(canvas, { artifact_id: "a1" });

    expect(put(canvas, { artifact_id: null })).toEqual({ status: 200, body: null });
    expect(get(canvas).body).toBeNull();
    // Closing what was never open is still a close.
    expect(put(canvas, { artifact_id: null }, "c2")).toEqual({ status: 200, body: null });
  });

  it("answers 404 for a canvas that is not there, and keeps what was open", () => {
    const canvas = server();
    put(canvas, { artifact_id: "a1" });

    expect(put(canvas, { artifact_id: "gone" })).toEqual({ status: 404, body: { detail: "artifact not found" } });
    expect(get(canvas).body).toEqual({ artifact_id: "a1", selection: null });
  });

  it.each<[string, unknown]>([
    ["a selection with no canvas to be in", { artifact_id: null, selection: PICK }],
    ["a version the canvas does not have yet", { artifact_id: "a1", selection: { ...PICK, version: 2 } }],
    ["version zero", { artifact_id: "a1", selection: { ...PICK, version: 0 } }],
    ["blank text", { artifact_id: "a1", selection: { ...PICK, text: " \n " } }],
    ["lines in the wrong order", { artifact_id: "a1", selection: { ...PICK, line_start: 3, line_end: 2 } }],
    ["more text than a message holds", { artifact_id: "a1", selection: { ...PICK, text: "x".repeat(20001) } }],
    ["a selection that is not a passage", { artifact_id: "a1", selection: "chạy 5 km" }],
    ["a line number that is not whole", { artifact_id: "a1", selection: { ...PICK, line_end: 2.5 } }],
    ["no canvas field at all", { selection: null }],
  ])("refuses %s with a 422 and changes nothing", (_name, body) => {
    const canvas = server();
    put(canvas, { artifact_id: "a2" });

    expect(put(canvas, body).status).toBe(422);
    expect(get(canvas).body).toEqual({ artifact_id: "a2", selection: null });
  });

  it("takes the most text a message holds, counted in characters", () => {
    const canvas = server();
    expect(put(canvas, { artifact_id: "a1", selection: { ...PICK, text: "x".repeat(20000) } }).status).toBe(200);
    // 20000 characters, though twice that many UTF-16 units.
    expect(put(canvas, { artifact_id: "a1", selection: { ...PICK, text: "😀".repeat(20000) } }).status).toBe(200);
  });

  it("forgets a canvas that is deleted: nothing is open on it any more", () => {
    const canvas = server();
    put(canvas, { artifact_id: "a1" });
    put(canvas, { artifact_id: "a1" }, "c2");

    canvas.remove("a1");

    expect([get(canvas).body, get(canvas, "c2").body]).toEqual([null, null]);
  });

  it("opens a canvas made in a conversation there, with nothing selected, and a canvas made alone nowhere", () => {
    const canvas = server();
    put(canvas, { artifact_id: "a1", selection: PICK });

    plain(canvas.route("/artifacts", "POST", { title: "Một mình", kind: "markdown" }, new URLSearchParams()));
    expect(get(canvas).body).toEqual({ artifact_id: "a1", selection: PICK });

    const made = plain(canvas.route("/artifacts", "POST", { title: "Mới", kind: "markdown", conversation_id: "c1" }, new URLSearchParams()));
    const { id } = made.body as { id: string };
    expect(get(canvas).body).toEqual({ artifact_id: id, selection: null });
  });

  it("holds a read like any other canvas request, and answers with what is open when it is let go", async () => {
    const canvas = server();
    const release = canvas.holdNext("GET /conversations/c1/canvas");
    const held = canvas.focusRoute("c1", "GET", null);
    put(canvas, { artifact_id: "a1" });

    await release();

    expect(await held).toEqual({ status: 200, body: { artifact_id: "a1", selection: null } });
  });

  it("refuses and loses on demand, and answers a method it has no route for with 405", () => {
    const canvas = server();
    canvas.refuseNext("PUT /conversations/c1/canvas", 500);
    expect(put(canvas, { artifact_id: "a1" })).toEqual({ status: 500, text: "Internal Server Error" });
    expect(get(canvas).body).toBeNull();

    canvas.loseNext("PUT /conversations/c1/canvas");
    expect(canvas.focusRoute("c1", "PUT", { artifact_id: "a1" })).toBe("lost");
    expect(get(canvas).body).toEqual({ artifact_id: "a1", selection: null });

    expect(plain(canvas.focusRoute("c1", "DELETE", null)).status).toBe(405);
  });
});

describe("FakeCanvas message canvas", () => {
  it("leaves the focus alone when the message carries no canvas, or a null one", () => {
    const canvas = server();
    put(canvas, { artifact_id: "a1", selection: PICK });

    expect(canvas.applyMessageCanvas("c1", undefined)).toBeNull();
    expect(canvas.applyMessageCanvas("c1", null)).toBeNull();

    expect(get(canvas).body).toEqual({ artifact_id: "a1", selection: PICK });
  });

  it("closes on a null canvas id, opens and shares a real one, and closes on one that is gone", () => {
    const canvas = server();
    put(canvas, { artifact_id: "a1" });

    expect(canvas.applyMessageCanvas("c1", { artifact_id: null })).toBeNull();
    expect(get(canvas).body).toBeNull();

    expect(canvas.applyMessageCanvas("c1", { artifact_id: "a2", selection: null })).toBeNull();
    expect(get(canvas).body).toEqual({ artifact_id: "a2", selection: null });
    // Opening one canvas does not unlink the one before it: both stay shared with the conversation.
    const listed = plain(canvas.route("/artifacts", "GET", null, new URLSearchParams({ conversation_id: "c1" })));
    expect((listed.body as { id: string }[]).map((c) => c.id)).toEqual(["a2", "a1"]);

    // A message still goes when its canvas was deleted meanwhile; it only closes the focus.
    expect(canvas.applyMessageCanvas("c1", { artifact_id: "gone" })).toBeNull();
    expect(get(canvas).body).toBeNull();
  });

  it("takes the selection a message carries, and a message without one clears the last", () => {
    const canvas = server();
    canvas.applyMessageCanvas("c1", { artifact_id: "a1", selection: PICK });
    expect(get(canvas).body).toEqual({ artifact_id: "a1", selection: PICK });

    canvas.applyMessageCanvas("c1", { artifact_id: "a1" });
    expect(get(canvas).body).toEqual({ artifact_id: "a1", selection: null });
  });

  it("refuses a selection the note would drop with a 422, and applies nothing", () => {
    const canvas = server();
    put(canvas, { artifact_id: "a2" });

    expect(refusal(canvas.applyMessageCanvas("c1", { artifact_id: "a1", selection: { ...PICK, version: 9 } })).status).toBe(422);
    expect(refusal(canvas.applyMessageCanvas("c1", { artifact_id: null, selection: PICK })).status).toBe(422);
    expect(refusal(canvas.applyMessageCanvas("c1", "a1")).status).toBe(422);

    expect(get(canvas).body).toEqual({ artifact_id: "a2", selection: null });
  });
});

describe("FakeBackend message canvas", () => {
  const send = (backend: FakeBackend, id: string, body: unknown) =>
    backend.fetch(`/api/conversations/${id}/messages`, { method: "POST", body: JSON.stringify(body) });

  it("applies the canvas a message carries before it goes on, and keeps it when it carries none", async () => {
    const backend = new FakeBackend();
    backend.canvas.add({ id: "a1" });
    const { id } = backend.create();

    expect((await send(backend, id, { text: "một", canvas: { artifact_id: "a1", selection: null } })).status).toBe(200);
    expect(backend.canvas.focus.of(id)).toEqual({ artifact_id: "a1", selection: null });

    expect((await send(backend, id, { text: "hai" })).status).toBe(200);
    expect(backend.canvas.focus.of(id)).toEqual({ artifact_id: "a1", selection: null });
  });

  it("refuses the whole message with a 422 when its selection does not fit, storing nothing", async () => {
    const backend = new FakeBackend();
    backend.canvas.add({ id: "a1" });
    const { id } = backend.create();

    const reply = await send(backend, id, { text: "một", canvas: { artifact_id: "a1", selection: { ...PICK, version: 9 } } });

    expect(reply.status).toBe(422);
    expect(backend.canvas.focus.of(id)).toBeNull();
    expect((await (await backend.fetch(`/api/conversations/${id}`)).json()).messages).toEqual([]);
  });

  it("serves the focus routes of a conversation that exists, and 404s one that does not", async () => {
    const backend = new FakeBackend();
    backend.canvas.add({ id: "a1" });
    const { id } = backend.create();

    const put = await backend.fetch(`/api/conversations/${id}/canvas`, { method: "PUT", body: JSON.stringify({ artifact_id: "a1" }) });
    expect([put.status, await put.json()]).toEqual([200, { artifact_id: "a1", selection: null }]);
    const read = await backend.fetch(`/api/conversations/${id}/canvas`);
    expect(await read.json()).toEqual({ artifact_id: "a1", selection: null });
    expect(backend.requests.map((r) => `${r.method} ${r.path}`)).toEqual([
      `PUT /conversations/${id}/canvas`,
      `GET /conversations/${id}/canvas`,
    ]);

    expect((await backend.fetch("/api/conversations/nope/canvas")).status).toBe(404);
  });
});
