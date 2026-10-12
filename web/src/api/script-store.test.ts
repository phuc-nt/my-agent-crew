import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { ApiError } from "./client";
import { scriptStoreApi } from "./script-store";

/** What each call asked for, as "<METHOD> <address>". */
let asked: string[];
let answer: () => Response;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

beforeEach(() => {
  asked = [];
  answer = () => json({});
  vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init: RequestInit = {}) => {
    asked.push(`${init.method ?? "GET"} ${String(input)}`);
    return answer();
  });
});

/** The query of the one request made, as the server would read it. */
const sent = () => Object.fromEntries(new URL(asked[0].split(" ")[1], "http://crew").searchParams);

describe("the script store's requests", () => {
  it("lists one agent's store, whatever its id holds", async () => {
    answer = () => json({ limit_chars: 262_144, namespaces: [] });

    expect(await scriptStoreApi.list("a b/c")).toEqual({ limit_chars: 262_144, namespaces: [] });
    expect(asked).toEqual(["GET /api/agents/a%20b%2Fc/script-store"]);
  });

  it("reads one value by its namespace and its key, each sent whole", async () => {
    answer = () => json({ namespace: "conv:1", key: "k", text: "1", chars: 1, updated_at: "" });

    await scriptStoreApi.value("coach", "job:a&b", "đơn #1?x=y&z");

    expect(asked[0]).toMatch(/^GET \/api\/agents\/coach\/script-store\/value\?/);
    expect(sent()).toEqual({ namespace: "job:a&b", key: "đơn #1?x=y&z" });
  });

  it("deletes one key by its namespace and its key", async () => {
    answer = () => json({ deleted: 1 });

    expect(await scriptStoreApi.remove("coach", "job:brief", "seen&more=1")).toEqual({ deleted: 1 });
    expect(asked[0]).toMatch(/^DELETE \/api\/agents\/coach\/script-store\?/);
    expect(sent()).toEqual({ namespace: "job:brief", key: "seen&more=1" });
  });

  it("deletes a whole namespace only when no key is named", async () => {
    answer = () => json({ deleted: 3 });

    await scriptStoreApi.remove("coach", "job:brief");

    expect(sent()).toEqual({ namespace: "job:brief" });
  });

  // A key that fell out of the address would take every other key of the namespace with it.
  it("still names the key when the key is empty, so one row is asked for and never all of them", async () => {
    await scriptStoreApi.remove("coach", "job:brief", "");
    await scriptStoreApi.value("coach", "job:brief", "");

    expect(asked[0]).toBe("DELETE /api/agents/coach/script-store?namespace=job%3Abrief&key=");
    expect(asked[1]).toBe("GET /api/agents/coach/script-store/value?namespace=job%3Abrief&key=");
  });

  it("fails with the server's status and words", async () => {
    answer = () => json({ detail: "key not found" }, 404);

    const failure = await scriptStoreApi.value("coach", "job:brief", "seen").catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({ status: 404, message: "key not found" });
  });
});
