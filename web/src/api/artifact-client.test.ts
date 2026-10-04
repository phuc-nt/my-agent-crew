import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import { artifactApi, conflictHeadOf, conflictOf, sizeCapOf, storageFullOf, versionGoneOf } from "./artifact-client";
import type { ArtifactDetail } from "./artifact-types";
import { ApiError } from "./client";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

const fetchMock = vitest.fn<typeof fetch>();
vitest.stubGlobal("fetch", fetchMock);

afterEach(() => fetchMock.mockReset());

/** The url, method, JSON body and init of the `n`-th fetch. */
function sent(n = 0) {
  const [url, init] = fetchMock.mock.calls[n];
  return { url, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : undefined, init };
}

const detail: ArtifactDetail = {
  id: "a1",
  title: "Kế hoạch",
  kind: "markdown",
  language: "",
  agent_id: "",
  head_version: 1,
  source: "",
  created_at: "2026-10-02T03:00:00+00:00",
  updated_at: "2026-10-02T03:00:00+00:00",
  head_author: "user",
  content: "",
  conversation_ids: ["c1"],
};

describe("artifactApi", () => {
  it("lists every canvas, a conversation's, or those whose title holds a query", async () => {
    fetchMock.mockImplementation(async () => jsonResponse([]));
    await artifactApi.list();
    await artifactApi.list("c 1");
    await artifactApi.list("c1", "kế hoạch");
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/artifacts",
      "/api/artifacts?conversation_id=c+1",
      "/api/artifacts?conversation_id=c1&q=k%E1%BA%BF+ho%E1%BA%A1ch",
    ]);
  });

  it("creates a canvas in a conversation and returns its detail", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(detail, 201));
    const made = await artifactApi.create({ title: "Kế hoạch", kind: "markdown", content: "", conversation_id: "c1" });
    expect(made).toEqual(detail);
    expect(sent()).toMatchObject({
      url: "/api/artifacts",
      method: "POST",
      body: { title: "Kế hoạch", kind: "markdown", content: "", conversation_id: "c1" },
    });
  });

  it("reads, saves, renames, restores and lists versions under an encoded id", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({}));
    await artifactApi.get("a/1");
    await artifactApi.save("a/1", "chữ", 3);
    await artifactApi.rename("a/1", "Mới");
    await artifactApi.restore("a/1", 2);
    await artifactApi.versions("a/1");
    await artifactApi.version("a/1", 4);
    const calls = fetchMock.mock.calls.map((_, n) => sent(n));
    expect(calls.map(({ method, url, body }) => [method, url, body])).toEqual([
      ["GET", "/api/artifacts/a%2F1", undefined],
      ["PUT", "/api/artifacts/a%2F1", { content: "chữ", base_version: 3 }],
      ["PATCH", "/api/artifacts/a%2F1", { title: "Mới" }],
      ["POST", "/api/artifacts/a%2F1/restore", { version: 2 }],
      ["GET", "/api/artifacts/a%2F1/versions", undefined],
      ["GET", "/api/artifacts/a%2F1/versions/4", undefined],
    ]);
  });

  it("asks for a canvas's file to be read again, on the version the text stands on", async () => {
    const summary = { ...detail, head_version: 4, source: "workspace:master/a.md" };
    fetchMock.mockResolvedValueOnce(jsonResponse({ changed: true, artifact: summary }));

    expect(await artifactApi.reimport("a/1", 3)).toEqual({ changed: true, artifact: summary });
    expect(sent()).toMatchObject({ url: "/api/artifacts/a%2F1/reimport", method: "POST", body: { base_version: 3 } });
  });

  it("passes a read's signal, a re-import's, and a save's signal and keepalive, through to fetch", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({}));
    const read = new AbortController();
    const save = new AbortController();
    const again = new AbortController();
    await artifactApi.get("a1", read.signal);
    await artifactApi.save("a1", "x", 1, { signal: save.signal, keepalive: true });
    await artifactApi.save("a1", "y", 2);
    await artifactApi.reimport("a1", 2, again.signal);
    expect(sent(0).init?.signal).toBe(read.signal);
    expect(sent(1).init).toMatchObject({ signal: save.signal, keepalive: true });
    expect(sent(2).init?.keepalive).toBeFalsy();
    expect(sent(3).init?.signal).toBe(again.signal);
  });

  it("links the raw text of the newest version, of one version, and as a download", () => {
    expect(artifactApi.rawUrl("a/1")).toBe("/api/artifacts/a%2F1/raw");
    expect(artifactApi.rawUrl("a1", { version: 3 })).toBe("/api/artifacts/a1/raw?version=3");
    expect(artifactApi.rawUrl("a1", { download: true })).toBe("/api/artifacts/a1/raw?download=1");
  });

  it("links the page of a canvas under an encoded id, with no version: the newest is the one shown", () => {
    expect(artifactApi.renderUrl("a/1")).toBe("/api/artifacts/a%2F1/render");
    expect(artifactApi.renderUrl("a1")).toBe("/api/artifacts/a1/render");
  });

  it("sends the kind a canvas is made as, with the text it starts from", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ...detail, kind: "html" }, 201));
    await artifactApi.create({ title: "Trang", kind: "html", content: "<p>x</p>", conversation_id: "c1" });

    expect(sent()).toMatchObject({
      url: "/api/artifacts",
      method: "POST",
      body: { title: "Trang", kind: "html", content: "<p>x</p>", conversation_id: "c1" },
    });
  });

  it("reads the detail of an image, which has no text", async () => {
    const image = { ...detail, kind: "image", content: null };
    fetchMock.mockResolvedValueOnce(jsonResponse(image));

    expect(await artifactApi.get("a1")).toEqual(image);
  });

  it("reads what a conversation has open, null when nothing, and sets or closes it under an encoded id", async () => {
    const open = { artifact_id: "0123456789ab", selection: null };
    fetchMock
      .mockResolvedValueOnce(jsonResponse(open))
      .mockResolvedValueOnce(jsonResponse(null))
      .mockResolvedValueOnce(jsonResponse(open))
      .mockResolvedValueOnce(jsonResponse(null));

    expect(await artifactApi.getFocus("c/1")).toEqual(open);
    expect(await artifactApi.getFocus("c1")).toBeNull();
    expect(await artifactApi.putFocus("c/1", { artifact_id: "0123456789ab" })).toEqual(open);
    expect(await artifactApi.putFocus("c1", { artifact_id: null })).toBeNull();

    const calls = fetchMock.mock.calls.map((_, n) => sent(n));
    expect(calls.map(({ method, url, body }) => [method, url, body])).toEqual([
      ["GET", "/api/conversations/c%2F1/canvas", undefined],
      ["GET", "/api/conversations/c1/canvas", undefined],
      ["PUT", "/api/conversations/c%2F1/canvas", { artifact_id: "0123456789ab" }],
      ["PUT", "/api/conversations/c1/canvas", { artifact_id: null }],
    ]);
  });

  it("rejects a focus request the server refused, with its status", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "artifact not found" }, 404));
    await expect(artifactApi.putFocus("c1", { artifact_id: "gone" })).rejects.toMatchObject({
      status: 404,
      message: "artifact not found",
    });
  });
});

describe("canvas error shapes", () => {
  it("reads the server's version from a 409 that carries one, and from nothing else", () => {
    const body = { head_version: 7, content: "theirs", author: "agent:ming" };
    expect(conflictOf(new ApiError(409, JSON.stringify(body), body))).toEqual(body);
    expect(conflictOf(new ApiError(409, "conversation is busy", "conversation is busy"))).toBeNull();
    expect(conflictOf(new ApiError(412, "", body))).toBeNull();
    expect(conflictOf(new ApiError(409, "", { ...body, head_version: "7" }))).toBeNull();
    expect(conflictOf(new ApiError(409, "", { ...body, content: null }))).toBeNull();
    expect(conflictOf(new TypeError("Failed to fetch"))).toBeNull();
  });

  it("reads the newest version alone from a 409, which a picture's carries with no text", () => {
    const body = { head_version: 7, content: null, author: "user" };
    expect(conflictHeadOf(new ApiError(409, JSON.stringify(body), body))).toBe(7);
    expect(conflictHeadOf(new ApiError(409, "", { head_version: 7 }))).toBe(7);
    expect(conflictHeadOf(new ApiError(409, "", { ...body, head_version: "7" }))).toBeNull();
    expect(conflictHeadOf(new ApiError(409, "conversation is busy", "conversation is busy"))).toBeNull();
    expect(conflictHeadOf(new ApiError(412, "", body))).toBeNull();
    expect(conflictHeadOf(new TypeError("Failed to fetch"))).toBeNull();
  });

  it("reads a full store's usage and its largest canvases from a 507", () => {
    const body = { used: 900, cap: 1000, largest: [{ id: "a1", title: "Big", size: 600 }] };
    expect(storageFullOf(new ApiError(507, "", body))).toEqual(body);
    expect(storageFullOf(new ApiError(507, "Insufficient Storage", "Insufficient Storage"))).toBeNull();
    expect(storageFullOf(new ApiError(500, "", body))).toBeNull();
    expect(storageFullOf(new ApiError(507, "", { ...body, largest: null }))).toBeNull();
  });

  it("reads the cap a 413 holds the canvas to, and from nothing else", () => {
    const body = { size: 5_000_000, cap: 4 * 1024 * 1024 };
    expect(sizeCapOf(new ApiError(413, JSON.stringify(body), body))).toBe(4 * 1024 * 1024);
    expect(sizeCapOf(new ApiError(413, "too large", "too large"))).toBeNull();
    expect(sizeCapOf(new ApiError(413, "", { size: 5_000_000 }))).toBeNull();
    expect(sizeCapOf(new ApiError(413, "", { ...body, cap: "4 MB" }))).toBeNull();
    expect(sizeCapOf(new ApiError(413, "", [body]))).toBeNull();
    expect(sizeCapOf(new ApiError(422, "", body))).toBeNull();
    expect(sizeCapOf(new TypeError("Failed to fetch"))).toBeNull();
  });

  it("tells a version that was folded away from a canvas that is gone", () => {
    expect(versionGoneOf(new ApiError(404, "", { head_version: 9 }))).toBe(9);
    expect(versionGoneOf(new ApiError(404, "artifact not found", "artifact not found"))).toBeNull();
    expect(versionGoneOf(new ApiError(410, "", { head_version: 9 }))).toBeNull();
    expect(versionGoneOf(new Error("boom"))).toBeNull();
  });
});
