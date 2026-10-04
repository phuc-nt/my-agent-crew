import type { ArtifactSummary, ArtifactVersion } from "../api/artifact-types";
import { type FakeReply, invalid, ok, refused } from "./fake-canvas-faults";

/** As much of a canvas as reading its file again needs. */
type Sourced = { summary: ArtifactSummary; versions: ArtifactVersion[] };

const WORKSPACE = /^workspace:[^/]+\/.+$/;
const bytes = (text: string) => new TextEncoder().encode(text).length;

/**
 * The workspace files canvases were imported from, and `POST /artifacts/{id}/reimport` as the
 * server answers it: the canvas names the file, a file that holds what the newest version holds
 * adds no version, and a file that differs becomes the person's next version unless something
 * was saved since the version the request names. A file the server refuses to read is answered
 * with a sentence, never with the sizes a refused save carries.
 */
export class SourceFiles<Canvas extends Sourced> {
  private files = new Map<string, string>();

  constructor(
    /** The most a version of this kind may hold, in bytes. */
    private cap: (kind: string) => number,
    /** Writes the file as the person's next version; the reply is the store's own when it refuses. */
    private store: (canvas: Canvas, content: string) => FakeReply,
  ) {}

  /** What the file a `source` names holds now; null takes the file away. */
  put(source: string, text: string | null): void {
    if (text === null) this.files.delete(source);
    else this.files.set(source, text.replace(/\r\n?/g, "\n"));
  }

  reimport(canvas: Canvas | undefined, baseVersion: unknown): FakeReply {
    if (!Number.isInteger(baseVersion) || (baseVersion as number) < 1) return invalid("base_version");
    if (!canvas) return refused(404, "artifact not found");
    const { source, kind } = canvas.summary;
    if (!WORKSPACE.test(source)) return refused(422, "the canvas records no workspace file");
    const text = this.files.get(source);
    if (text === undefined) return refused(410, "the source file is gone");
    if (bytes(text) > this.cap(kind)) return refused(413, "the source file is over the cap of its kind");
    const head = canvas.versions[canvas.versions.length - 1];
    if (text !== head.content) {
      if (baseVersion !== head.version) {
        return refused(409, { head_version: head.version, content: head.content, author: head.author });
      }
      const reply = this.store(canvas, text);
      if (reply === "lost" || reply.status !== 200) return reply;
    }
    return ok({ changed: text !== head.content, artifact: { ...canvas.summary } });
  }
}
