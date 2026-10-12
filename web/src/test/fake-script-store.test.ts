import { describe, expect, it } from "vitest";
import type { ScriptStoreInfo } from "../api/script-store";
import { FakeScriptStore } from "./fake-script-store";

const BASE = "/agents/coach/script-store";
const named = (namespace: string, key?: string) => new URLSearchParams(key === undefined ? { namespace } : { namespace, key });
const none = new URLSearchParams();
const list = (store: FakeScriptStore, agentId = "coach") =>
  store.route(`/agents/${agentId}/script-store`, "GET", none)?.body as ScriptStoreInfo;

describe("the script-store routes both fakes answer", () => {
  it("lists namespaces by name and keys by key, each value as compact JSON text", () => {
    const store = new FakeScriptStore()
      .keep("coach", "job:brief", "seen", ["a1", "b2"], "2026-10-11T23:40:00+00:00")
      .keep("coach", "job:brief", "count", { n: 2 })
      .keep("coach", "conv:c1", "draft", "nháp");

    expect(list(store)).toEqual({
      limit_chars: 262_144,
      namespaces: [
        {
          namespace: "conv:c1", kind: "conv", ref: "c1", title: null, orphan: true, chars: 11,
          entries: [{ key: "draft", preview: '"nháp"', chars: 6, updated_at: "2026-10-12T01:00:00+00:00" }],
        },
        {
          namespace: "job:brief", kind: "job", ref: "brief", title: null, orphan: true, chars: 27,
          entries: [
            { key: "count", preview: '{"n":2}', chars: 7, updated_at: "2026-10-12T01:00:00+00:00" },
            { key: "seen", preview: '["a1","b2"]', chars: 11, updated_at: "2026-10-11T23:40:00+00:00" },
          ],
        },
      ],
    });
  });

  it("keeps each agent's rows to that agent", () => {
    const store = new FakeScriptStore().keep("coach", "job:brief", "seen", 1);

    expect(list(store, "default")).toEqual({ limit_chars: 262_144, namespaces: [] });
  });

  it("cuts a preview at 200 characters and marks the cut, and measures the value whole", () => {
    const store = new FakeScriptStore().keepText("coach", "job:brief", "long", "x".repeat(201)).keepText("coach", "job:brief", "fits", "y".repeat(200));
    const [fits, long] = list(store).namespaces[0].entries;

    expect(long).toMatchObject({ preview: `${"x".repeat(200)}…`, chars: 201 });
    expect(fits).toMatchObject({ preview: "y".repeat(200), chars: 200 });
  });

  it("says whose a namespace is from the crew and the conversations it is pointed at", () => {
    const store = new FakeScriptStore().keep("coach", "job:brief", "k", 1).keep("coach", "job:gone", "k", 1);
    store.keep("coach", "conv:c1", "k", 1).keep("coach", "conv:untitled", "k", 1).keep("coach", "misc", "k", 1).keep("coach", "team:a:b", "k", 1);
    store.schedule = (agentId, scheduleId) => (agentId === "coach" && scheduleId === "brief" ? { name: "Bản tin sáng" } : undefined);
    store.conversation = (id) => (id === "c1" ? { title: "Đơn mới" } : id === "untitled" ? { title: "" } : undefined);

    const whose = Object.fromEntries(list(store).namespaces.map((held) => [held.namespace, [held.kind, held.ref, held.title, held.orphan]]));
    expect(whose).toEqual({
      "job:brief": ["job", "brief", "Bản tin sáng", false],
      "job:gone": ["job", "gone", null, true],
      "conv:c1": ["conv", "c1", "Đơn mới", false],
      // There, and never given a title: not an orphan.
      "conv:untitled": ["conv", "untitled", null, false],
      misc: ["other", "misc", null, false],
      "team:a:b": ["other", "team:a:b", null, false],
    });
  });

  it("answers as the server did before it said what a namespace is", () => {
    const store = new FakeScriptStore().keep("coach", "job:brief", "seen", 1);
    store.old = true;

    expect(list(store)).toEqual({
      namespaces: [{ namespace: "job:brief", chars: 5, entries: [{ key: "seen", preview: "1", chars: 1, updated_at: "2026-10-12T01:00:00+00:00" }] }],
    });
  });

  it("reads one value whole, and answers 404 for a key or a namespace it does not hold", () => {
    const store = new FakeScriptStore().keepText("coach", "job:brief", "long", "x".repeat(300), "2026-10-11T23:40:00+00:00");

    expect(store.route(`${BASE}/value`, "GET", named("job:brief", "long"))).toEqual({
      status: 200,
      body: { namespace: "job:brief", key: "long", text: "x".repeat(300), chars: 300, updated_at: "2026-10-11T23:40:00+00:00" },
    });
    expect(store.route(`${BASE}/value`, "GET", named("job:brief", "other"))).toEqual({ status: 404, body: { detail: "key not found" } });
    expect(store.route(`${BASE}/value`, "GET", named("job:else", "long"))).toEqual({ status: 404, body: { detail: "key not found" } });
  });

  it("deletes one key, and stops listing a namespace once its last key is gone", () => {
    const store = new FakeScriptStore().keep("coach", "job:brief", "a", 1).keep("coach", "job:brief", "b", 2);

    expect(store.route(BASE, "DELETE", named("job:brief", "a"))).toEqual({ status: 200, body: { deleted: 1 } });
    expect(store.keys("coach", "job:brief")).toEqual(["b"]);
    expect(store.route(BASE, "DELETE", named("job:brief", "b"))).toEqual({ status: 200, body: { deleted: 1 } });
    expect(list(store).namespaces).toEqual([]);
  });

  it("deletes a whole namespace when no key is named, and only that one", () => {
    const store = new FakeScriptStore().keep("coach", "job:brief", "a", 1).keep("coach", "job:brief", "b", 2).keep("coach", "conv:c1", "a", 3);

    expect(store.route(BASE, "DELETE", named("job:brief"))).toEqual({ status: 200, body: { deleted: 2 } });
    expect(store.keys("coach", "job:brief")).toEqual([]);
    expect(store.keys("coach", "conv:c1")).toEqual(["a"]);
  });

  // An empty key is a key: it names one row, never the namespace.
  it("takes an empty key as naming one key", () => {
    const store = new FakeScriptStore().keep("coach", "job:brief", "", 1).keep("coach", "job:brief", "b", 2);

    expect(store.route(BASE, "DELETE", named("job:brief", ""))).toEqual({ status: 200, body: { deleted: 1 } });
    expect(store.keys("coach", "job:brief")).toEqual(["b"]);
  });

  it("answers 200 with nothing deleted when nothing matched", () => {
    const store = new FakeScriptStore().keep("coach", "job:brief", "a", 1);

    expect(store.route(BASE, "DELETE", named("job:brief", "ghost"))).toEqual({ status: 200, body: { deleted: 0 } });
    expect(store.route(BASE, "DELETE", named("job:ghost"))).toEqual({ status: 200, body: { deleted: 0 } });
    expect(store.keys("coach", "job:brief")).toEqual(["a"]);
  });

  it("answers 404 for an agent the crew does not have, on each route", () => {
    const store = new FakeScriptStore().keep("ghost", "job:brief", "a", 1);
    store.knownAgent = (agentId) => agentId === "coach";
    const gone = { status: 404, body: { detail: "agent not found" } };

    expect(store.route("/agents/ghost/script-store", "GET", none)).toEqual(gone);
    expect(store.route("/agents/ghost/script-store/value", "GET", named("job:brief", "a"))).toEqual(gone);
    expect(store.route("/agents/ghost/script-store", "DELETE", named("job:brief"))).toEqual(gone);
    expect(store.keys("ghost", "job:brief")).toEqual(["a"]);
  });

  it("refuses a kind of request for as long as it is told to, and changes nothing meanwhile", () => {
    const store = new FakeScriptStore().keep("coach", "job:brief", "a", 1);
    store.refuse.remove = { status: 500, detail: "database is locked" };

    expect(store.route(BASE, "DELETE", named("job:brief", "a"))).toEqual({ status: 500, body: { detail: "database is locked" } });
    expect(store.route(BASE, "DELETE", named("job:brief", "a"))?.status).toBe(500);
    expect(store.keys("coach", "job:brief")).toEqual(["a"]);
    expect(store.route(BASE, "GET", none)?.status).toBe(200);

    store.refuse = {};
    expect(store.route(BASE, "DELETE", named("job:brief", "a"))).toEqual({ status: 200, body: { deleted: 1 } });
  });

  it("turns away a request that does not say which namespace or which key", () => {
    const store = new FakeScriptStore().keep("coach", "job:brief", "a", 1);

    expect(store.route(BASE, "DELETE", none)?.status).toBe(422);
    expect(store.route(`${BASE}/value`, "GET", named("job:brief"))?.status).toBe(422);
    expect(store.keys("coach", "job:brief")).toEqual(["a"]);
  });

  it("leaves every other path to the fake it sits in, and other methods to nobody", () => {
    const store = new FakeScriptStore();

    expect(store.route("/agents/coach", "GET", none)).toBeNull();
    expect(store.route("/agents/coach/script-store/else", "GET", none)).toBeNull();
    expect(store.route("/script-store", "GET", none)).toBeNull();
    expect(store.route(BASE, "POST", none)?.status).toBe(405);
    expect(store.route(`${BASE}/value`, "DELETE", named("job:brief", "a"))?.status).toBe(405);
  });
});
