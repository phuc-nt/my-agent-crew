/** What a canvas route answers. "lost" means the work was done and the reply never came back. */
export type FakeReply = { status: number; body?: unknown; text?: string } | "lost";

export const ok = (body: unknown, status = 200): FakeReply => ({ status, body });
export const refused = (status: number, detail: unknown): FakeReply => ({ status, body: { detail } });
/** A 422 the way the server's request validation words it, naming the field. */
export const invalid = (field: string, where = "body") =>
  refused(422, [{ type: "value_error", loc: [where, field], msg: `invalid ${field}` }]);

type Fault = { target: string } & (
  | { kind: "refuse"; status: number; detail?: unknown }
  | { kind: "lose" }
  | { kind: "hold"; when: "request" | "reply"; gate: Promise<void> }
);

/**
 * Faults queued for the next matching request. A target is a method ("PUT"), which any canvas
 * path matches, or a method and a path without its query ("GET /artifacts/a1").
 */
export class CanvasFaults {
  private queue: Fault[] = [];

  /** The next match is answered with `status` and nothing is done. */
  refuse(target: string, status: number, detail?: unknown): void {
    this.queue.push({ target, kind: "refuse", status, detail });
  }

  /** The next match is done, and its reply is lost on the way back. */
  lose(target: string): void {
    this.queue.push({ target, kind: "lose" });
  }

  /** "request": the next match is done only at release, as a request still on the wire.
   *  "reply": it is done at once and answered at release. The returned function opens the
   *  gate and resolves once the held work and reply have gone through. */
  hold(target: string, when: "request" | "reply"): () => Promise<void> {
    let open = () => {};
    const gate = new Promise<void>((resolve) => {
      open = resolve;
    });
    this.queue.push({ target, kind: "hold", when, gate });
    return () => {
      open();
      return gate.then(() => undefined);
    };
  }

  /** Runs `work` under the first fault aimed at this request, or plainly when none is. */
  run(
    method: string,
    path: string,
    work: () => FakeReply,
    refusal: (status: number, detail: unknown) => FakeReply,
  ): FakeReply | Promise<FakeReply> {
    const index = this.queue.findIndex((f) => f.target === method || f.target === `${method} ${path}`);
    if (index < 0) return work();
    const [fault] = this.queue.splice(index, 1);
    if (fault.kind === "refuse") return refusal(fault.status, fault.detail);
    if (fault.kind === "lose") {
      work();
      return "lost";
    }
    if (fault.when === "request") return fault.gate.then(work);
    const reply = work();
    return fault.gate.then(() => reply);
  }
}
