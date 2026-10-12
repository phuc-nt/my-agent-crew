import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { ScriptStoreInfo, ScriptStoreValue } from "../api/script-store";
import { useScriptStore } from "./use-script-store";

/** One function per request made, in the order asked; calling it answers that request. */
let answers: ((body: unknown, status?: number) => void)[];

beforeEach(() => {
  answers = [];
  vitest.stubGlobal(
    "fetch",
    () =>
      new Promise<Response>((resolve) => {
        answers.push((body, status = 200) =>
          resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } })),
        );
      }),
  );
});

const holding = (...namespaces: string[]): ScriptStoreInfo => ({
  namespaces: namespaces.map((namespace) => ({
    namespace,
    chars: 5,
    entries: [{ key: "seen", preview: "1", chars: 1, updated_at: "2026-10-12T01:00:00+00:00" }],
  })),
});
const listed = (store: ScriptStoreInfo | null) => store?.namespaces.map((held) => held.namespace);

describe("reading what an agent's scripts keep", () => {
  it("has nothing, and no failure, until the first read is answered", async () => {
    const { result } = renderHook(() => useScriptStore("coach"));
    expect(result.current.store).toBeNull();
    expect(result.current.failed).toBeNull();

    await act(async () => answers[0](holding("job:brief")));

    expect(listed(result.current.store)).toEqual(["job:brief"]);
  });

  // Two reads cross on a slow link: the one asked first knows less, whenever it lands.
  it("takes the answer to the last read alone, whichever comes back last", async () => {
    const { result } = renderHook(() => useScriptStore("coach"));
    act(() => void result.current.refresh());
    await waitFor(() => expect(answers).toHaveLength(2));

    await act(async () => answers[1](holding("job:newer")));
    await act(async () => answers[0](holding("job:older")));

    expect(listed(result.current.store)).toEqual(["job:newer"]);
  });

  it("does not report the failure of a read that a later one has replaced", async () => {
    const { result } = renderHook(() => useScriptStore("coach"));
    act(() => void result.current.refresh());
    await waitFor(() => expect(answers).toHaveLength(2));

    await act(async () => answers[1](holding("job:newer")));
    await act(async () => answers[0]({ detail: "boom" }, 500));

    expect(result.current.failed).toBeNull();
    expect(listed(result.current.store)).toEqual(["job:newer"]);
  });

  it("keeps the list it had when a later read fails, and lets go of the failure once one succeeds", async () => {
    const { result } = renderHook(() => useScriptStore("coach"));
    await act(async () => answers[0](holding("job:brief")));

    act(() => void result.current.refresh());
    await waitFor(() => expect(answers).toHaveLength(2));
    await act(async () => answers[1]({ detail: "boom" }, 500));
    expect(result.current.failed).toMatchObject({ status: 500 });
    expect(listed(result.current.store)).toEqual(["job:brief"]);

    act(() => void result.current.refresh());
    await waitFor(() => expect(answers).toHaveLength(3));
    await act(async () => answers[2](holding("job:brief", "job:next")));
    expect(result.current.failed).toBeNull();
    expect(listed(result.current.store)).toEqual(["job:brief", "job:next"]);
  });

  it("takes rows out at once when told they are gone, a namespace with its last key, and reads again", async () => {
    const { result } = renderHook(() => useScriptStore("coach"));
    await act(async () => answers[0](holding("job:brief", "job:other")));

    act(() => result.current.drop("job:brief", "seen"));

    expect(listed(result.current.store)).toEqual(["job:other"]);
    expect(answers).toHaveLength(2);
  });

  it("leaves the list as it was when the key it is told is gone was never in it", async () => {
    const { result } = renderHook(() => useScriptStore("coach"));
    await act(async () => answers[0](holding("job:brief")));

    act(() => result.current.drop("job:brief", "ghost"));
    act(() => result.current.drop("job:ghost"));

    expect(result.current.store).toEqual(holding("job:brief"));
  });

  it("changes nothing when the server refuses a delete, and hands the refusal to whoever asked", async () => {
    const { result } = renderHook(() => useScriptStore("coach"));
    await act(async () => answers[0](holding("job:brief")));

    let refusal: unknown;
    act(() => void result.current.remove("job:brief", "seen").catch((error: unknown) => (refusal = error)));
    await waitFor(() => expect(answers).toHaveLength(2));
    await act(async () => answers[1]({ detail: "database is locked" }, 500));

    expect(refusal).toMatchObject({ status: 500 });
    expect(listed(result.current.store)).toEqual(["job:brief"]);
    expect(result.current.failed).toBeNull();
    // No read followed: nothing changed to read.
    expect(answers).toHaveLength(2);
  });
});

describe("reading one key's value", () => {
  /** The value as the list of `holding` says it is: one character, written at one o'clock. */
  const asListed: ScriptStoreValue = { namespace: "job:brief", key: "seen", text: "1", chars: 1, updated_at: "2026-10-12T01:00:00+00:00" };

  async function reads(value: ScriptStoreValue, key = value.key) {
    const hook = renderHook(() => useScriptStore("coach"));
    await act(async () => answers[0](holding("job:brief")));
    let read: ScriptStoreValue | undefined;
    act(() => void hook.result.current.value("job:brief", key).then((answer) => (read = answer)));
    await waitFor(() => expect(answers).toHaveLength(2));
    return { ...hook, answer: () => act(async () => answers[1](value)), read: () => read };
  }

  it("hands back the text with its size and time, and reads nothing more when the list says the same", async () => {
    const { answer, read } = await reads(asListed);

    await answer();

    expect(read()).toEqual(asListed);
    expect(answers).toHaveLength(2);
  });

  it.each<[string, Partial<ScriptStoreValue>]>([
    ["of another size", { text: "12", chars: 2 }],
    ["written at another time", { updated_at: "2026-10-12T02:00:00+00:00" }],
  ])("reads the list again, once, for a value %s than the list says", async (_, since) => {
    const { answer, read, result } = await reads({ ...asListed, ...since });

    await answer();

    expect(read()).toEqual({ ...asListed, ...since });
    expect(answers).toHaveLength(3);
    const rewritten = holding("job:brief");
    rewritten.namespaces[0].entries[0] = { key: "seen", preview: "12", chars: 2, updated_at: "2026-10-12T02:00:00+00:00" };
    await act(async () => answers[2](rewritten));
    expect(result.current.store).toEqual(rewritten);
    expect(answers).toHaveLength(3);
  });

  it("reads nothing more for a key the list does not hold", async () => {
    const { answer } = await reads({ ...asListed, key: "unlisted", chars: 9 }, "unlisted");

    await answer();

    expect(answers).toHaveLength(2);
  });

  it("reads nothing more for an answer that comes after the screen closed", async () => {
    const { answer, unmount } = await reads({ ...asListed, chars: 9 });
    unmount();

    await answer();

    expect(answers).toHaveLength(2);
  });
});
