import type { ArtifactDetail, ArtifactEvent, ArtifactSummary, ArtifactVersion } from "../api/artifact-types";
import { fold } from "../components/conversation-search";
import { cleanTitle } from "../lib/canvas-title";
import { CanvasFaults, type FakeReply, invalid, ok, refused } from "./fake-canvas-faults";
import { FocusBook } from "./fake-canvas-focus";

export type { FakeReply } from "./fake-canvas-faults";

/** A canvas as if made earlier. `version` above 1 leaves a gap before it; `author` defaults to
 *  the creator. */
export type CanvasSeed = Partial<ArtifactSummary> & {
  content?: string;
  author?: string;
  version?: number;
  conversationIds?: string[];
};

type Canvas = { summary: ArtifactSummary; versions: ArtifactVersion[]; conversationIds: string[]; row: number };

const START = Date.parse("2026-10-02T03:00:00Z");
const USER = "user";
const LARGEST_SHOWN = 3;
const REASONS: Record<number, string> = { 502: "Bad Gateway", 503: "Service Unavailable", 504: "Gateway Timeout" };
const ROUTES: [RegExp, string[]][] = [
  [/^$/, ["GET", "PUT", "PATCH", "DELETE"]],
  [/^\/versions$/, ["GET"]],
  [/^\/versions\/\d+$/, ["GET"]],
  [/^\/restore$/, ["POST"]],
  [/^\/raw$/, ["GET"]],
];

const bytes = (text: string) => new TextEncoder().encode(text).length;
const lf = (text: string) => text.replace(/\r\n?/g, "\n");
const isVersion = (value: unknown) => Number.isInteger(value) && (value as number) >= 1;
const withoutText = ({ content: _content, ...meta }: ArtifactVersion) => meta;

/**
 * The canvas half of the fake server, shared by the vitest fetch and the Playwright routes.
 * It keeps the store's promises a client leans on (versions rise, a stale base gets the head,
 * a change is announced without its text) and seeds what folding leaves, gaps and versions
 * gone, without faking the fold rule itself.
 */
export class FakeCanvas {
  canvases = new Map<string, Canvas>();
  /** The most one version may hold, as the store caps markdown and code. */
  sizeCap = 512 * 1024;
  /** What every version of every canvas may hold together; an agent gets a tenth less. */
  storageCap = 1024 * 1024 * 1024;
  /** Hears each committed change as the activity stream would carry it. */
  onEvent: ((event: ArtifactEvent) => void) | null = null;
  conversationExists: (id: string) => boolean = () => true;
  /** The canvas each conversation has open, which a message, a `PUT` or a canvas made there sets. */
  focus = new FocusBook({
    head: (id) => this.canvases.get(id)?.summary.head_version,
    link: (id, conversationId) => {
      const { conversationIds } = this.get(id);
      if (!conversationIds.includes(conversationId)) conversationIds.push(conversationId);
    },
  });
  private faults = new CanvasFaults();
  private ticks = 0;
  private rows = 0;

  /** Seeds a canvas without announcing it. */
  add(seed: CanvasSeed = {}): ArtifactSummary {
    const { content = "", author, version = 1, conversationIds = [], ...fields } = seed;
    const row = ++this.rows;
    const now = this.now();
    const summary: ArtifactSummary = {
      ...{ id: this.freeId(), title: "Canvas", kind: "markdown", language: "", agent_id: "", source: "" },
      ...{ created_at: now, updated_at: now, ...fields, head_version: version },
    };
    const writer = author ?? (summary.agent_id ? `agent:${summary.agent_id}` : USER);
    const first = this.version(summary.id, version, lf(content), writer, "", summary.updated_at);
    this.canvases.set(summary.id, { summary, versions: [first], conversationIds: [...conversationIds], row });
    return { ...summary };
  }

  /** A write from outside this client, an agent's by default; `gap` skips that many numbers. */
  write(id: string, content: string, options: { author?: string; gap?: number } = {}): ArtifactVersion {
    return this.append(this.get(id), lf(content), options.author ?? "agent:master", "", options.gap ?? 0);
  }

  /** Drops a version the way a fold does; the head cannot go. */
  forget(id: string, version: number): void {
    const canvas = this.get(id);
    if (version === canvas.summary.head_version) throw new Error(`version ${version} is the head of ${id}`);
    canvas.versions = canvas.versions.filter((v) => v.version !== version);
  }

  /** A delete from outside this client. */
  remove(id: string): void {
    const { conversationIds } = this.get(id);
    this.canvases.delete(id);
    this.focus.forget(id);
    this.announce({ id, deleted: true }, conversationIds);
  }

  content(id: string): string {
    return this.head(this.get(id)).content;
  }

  refuseNext(target: string, status: number, detail?: unknown): void {
    this.faults.refuse(target, status, detail);
  }

  loseNext(target: string): void {
    this.faults.lose(target);
  }

  holdNext(target: string, when: "request" | "reply" = "request"): () => Promise<void> {
    return this.faults.hold(target, when);
  }

  /** Answers every `/artifacts…` path; null for any other. */
  route(path: string, method: string, body: unknown, params: URLSearchParams): FakeReply | Promise<FakeReply> | null {
    const match = path.match(/^\/artifacts(?:\/([^/]+)(\/.*)?)?$/);
    if (!match) return null;
    const id = match[1] === undefined ? null : decodeURIComponent(match[1]);
    const fields = typeof body === "object" && body !== null ? (body as Record<string, unknown>) : {};
    const work = () => (id === null ? this.top(method, fields, params) : this.one(id, match[2] ?? "", method, fields, params));
    return this.faults.run(method, path, work, (status, detail) => this.refusal(id, fields, status, detail));
  }

  /** `GET` and `PUT /conversations/{id}/canvas`, under the same faults as the other canvas routes. */
  focusRoute(conversationId: string, method: string, body: unknown): FakeReply | Promise<FakeReply> {
    const fields = typeof body === "object" && body !== null ? (body as Record<string, unknown>) : {};
    const work = () => {
      if (method === "GET") return ok(this.focus.of(conversationId));
      return method === "PUT" ? this.focus.put(conversationId, fields) : refused(405, "Method Not Allowed");
    };
    const path = `/conversations/${conversationId}/canvas`;
    return this.faults.run(method, path, work, (status, detail) => this.refusal(null, fields, status, detail));
  }

  /** The `canvas` a chat message carried, applied the way the server does after its gates:
   *  null when the message goes on, a 422 when the selection is one the note would drop. */
  applyMessageCanvas(conversationId: string, canvas: unknown): FakeReply | null {
    return this.focus.message(conversationId, canvas);
  }

  private top(method: string, body: Record<string, unknown>, params: URLSearchParams): FakeReply {
    if (method === "POST") return this.create(body);
    if (method !== "GET") return refused(405, "Method Not Allowed");
    const conversation = params.get("conversation_id");
    const needle = fold((params.get("q") ?? "").trim());
    const limit = Number(params.get("limit") ?? 50);
    if (!Number.isInteger(limit) || limit < 1 || limit > 200) return invalid("limit", "query");
    const found = [...this.canvases.values()]
      .filter((c) => conversation === null || c.conversationIds.includes(conversation))
      .filter((c) => !needle || fold(c.summary.title).includes(needle))
      .sort((a, b) => b.summary.updated_at.localeCompare(a.summary.updated_at) || b.row - a.row);
    return ok(found.slice(0, limit).map((c) => ({ ...c.summary })));
  }

  private create(body: Record<string, unknown>): FakeReply {
    const { title, kind, content = "", conversation_id: conversation = null } = body;
    if (typeof title !== "string") return invalid("title");
    if (kind !== "markdown" && kind !== "code") return invalid("kind");
    if (typeof content !== "string") return invalid("content");
    if (conversation !== null && typeof conversation !== "string") return invalid("conversation_id");
    if (conversation !== null && !this.conversationExists(conversation)) return refused(404, "conversation not found");
    const cleaned = cleanTitle(title);
    if (typeof cleaned !== "string") return refused(422, cleaned.problem);
    const refusal = this.refuseWrite(USER, bytes(lf(content)));
    if (refusal) return refusal;
    const summary = this.add({ title: cleaned, kind, content });
    this.announce(summary, []);
    if (conversation !== null) this.focus.open(conversation, summary.id);
    return ok(this.detail(this.get(summary.id)), 201);
  }

  private one(id: string, rest: string, method: string, body: Record<string, unknown>, params: URLSearchParams): FakeReply {
    const methods = ROUTES.find(([pattern]) => pattern.test(rest))?.[1];
    if (!methods) return refused(404, "Not Found");
    if (!methods.includes(method)) return refused(405, "Method Not Allowed");
    if (method === "PUT" && typeof body.content !== "string") return invalid("content");
    if (method === "PUT" && !isVersion(body.base_version)) return invalid("base_version");
    if (method === "PATCH" && typeof body.title !== "string") return invalid("title");
    if (rest === "/restore" && !isVersion(body.version)) return invalid("version");
    const title = method === "PATCH" ? cleanTitle(body.title as string) : "";
    if (typeof title !== "string") return refused(422, title.problem);
    const canvas = this.canvases.get(id);
    if (!canvas) return refused(404, "artifact not found");
    const gone = refused(404, { head_version: canvas.summary.head_version });
    const find = (version: number) => canvas.versions.find((v) => v.version === version);
    if (rest === "/versions") return ok(canvas.versions.map(withoutText).reverse());
    if (rest.startsWith("/versions/")) {
      const found = find(Number(rest.slice("/versions/".length)));
      return found ? ok({ ...found }) : gone;
    }
    if (rest === "/raw") {
      const asked = params.get("version");
      const found = asked === null ? this.head(canvas) : find(Number(asked));
      return found ? { status: 200, text: found.content } : gone;
    }
    if (rest === "/restore") {
      const found = find(body.version as number);
      return found ? this.store(canvas, found.content, `restore:${found.version}`) : gone;
    }
    if (method === "GET") return ok(this.detail(canvas));
    if (method === "DELETE") {
      this.remove(id);
      return { status: 204 };
    }
    if (method === "PATCH") {
      canvas.summary = { ...canvas.summary, title, updated_at: this.now() };
      this.announce({ ...canvas.summary }, canvas.conversationIds);
      return ok({ ...canvas.summary });
    }
    const head = this.head(canvas);
    if (body.base_version !== head.version) return refused(409, this.conflict(canvas));
    return this.store(canvas, lf(body.content as string), "");
  }

  private store(canvas: Canvas, content: string, note: string): FakeReply {
    return this.refuseWrite(USER, bytes(content)) ?? ok(withoutText(this.append(canvas, content, USER, note, 0)));
  }

  private refuseWrite(author: string, size: number): FakeReply | null {
    if (size > this.sizeCap) return refused(413, { size, cap: this.sizeCap });
    const cap = author === USER ? this.storageCap : Math.floor((this.storageCap * 9) / 10);
    return this.used() + size > cap ? refused(507, this.fullness(cap)) : null;
  }

  private refusal(id: string | null, body: Record<string, unknown>, status: number, detail: unknown): FakeReply {
    const canvas = id === null ? undefined : this.canvases.get(id);
    if (detail !== undefined) return refused(status, detail);
    if (status === 409 && canvas) return refused(409, this.conflict(canvas));
    if (status === 413) return refused(413, { size: bytes(String(body.content ?? "")), cap: this.sizeCap });
    if (status === 507) return refused(507, this.fullness(this.storageCap));
    if (status >= 500) return { status, text: REASONS[status] ?? "Internal Server Error" };
    return refused(status, status === 404 ? "artifact not found" : "refused");
  }

  private append(canvas: Canvas, content: string, author: string, note: string, gap: number): ArtifactVersion {
    const now = this.now();
    const next = this.version(canvas.summary.id, canvas.summary.head_version + 1 + gap, content, author, note, now);
    canvas.versions.push(next);
    canvas.summary = { ...canvas.summary, head_version: next.version, updated_at: now };
    this.announce({ ...canvas.summary }, canvas.conversationIds);
    return next;
  }

  private version(id: string, version: number, content: string, author: string, note: string, at: string): ArtifactVersion {
    return { artifact_id: id, version, size: bytes(content), author, conversation_id: "", note, created_at: at, updated_at: at, content };
  }

  private detail(canvas: Canvas): ArtifactDetail {
    const head = this.head(canvas);
    return { ...canvas.summary, head_author: head.author, content: head.content, conversation_ids: [...canvas.conversationIds] };
  }

  private conflict(canvas: Canvas) {
    const head = this.head(canvas);
    return { head_version: head.version, content: head.content, author: head.author };
  }

  private fullness(cap: number) {
    const sizes = [...this.canvases.values()].map((c) => ({
      ...{ id: c.summary.id, title: c.summary.title },
      size: c.versions.reduce((total, v) => total + v.size, 0),
    }));
    const largest = sizes.sort((a, b) => b.size - a.size || (a.id < b.id ? -1 : 1)).slice(0, LARGEST_SHOWN);
    return { used: this.used(), cap, largest };
  }

  private used(): number {
    return [...this.canvases.values()].reduce((total, c) => total + c.versions.reduce((sum, v) => sum + v.size, 0), 0);
  }

  private head(canvas: Canvas): ArtifactVersion {
    return canvas.versions[canvas.versions.length - 1];
  }

  private get(id: string): Canvas {
    const canvas = this.canvases.get(id);
    if (!canvas) throw new Error(`no canvas ${id}`);
    return canvas;
  }

  private freeId(): string {
    let n = this.rows;
    while (this.canvases.has(`a${n}`)) n += 1;
    return `a${n}`;
  }

  private announce(artifact: ArtifactEvent["artifact"], conversationIds: string[]): void {
    this.onEvent?.({ type: "artifact", artifact, conversation_ids: [...conversationIds] });
  }

  private now(): string {
    return `${new Date(START + this.ticks++ * 1000).toISOString().slice(0, 19)}+00:00`;
  }
}
