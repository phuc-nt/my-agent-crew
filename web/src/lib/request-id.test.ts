import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import { newRequestId } from "./request-id";

afterEach(() => vitest.unstubAllGlobals());

describe("the name a send goes under", () => {
  it("is thirty-two hex characters, which the server takes as a plain token", () => {
    const name = newRequestId();
    expect(name).toMatch(/^[0-9a-f]{32}$/);
    // What the server accepts: `^[A-Za-z0-9_-]*$`, sixty-four characters at most.
    expect(name).toMatch(/^[A-Za-z0-9_-]{1,64}$/);
  });

  it("is a new one each time", () => {
    const names = new Set(Array.from({ length: 200 }, newRequestId));
    expect(names.size).toBe(200);
  });

  it("is made where there is no randomUUID, and keeps the leading zero of a small byte", () => {
    // The home network serves the page over plain http, where `crypto.randomUUID` does not exist.
    vitest.stubGlobal("crypto", { getRandomValues: (bytes: Uint8Array) => bytes.fill(7) });
    expect(newRequestId()).toBe("07".repeat(16));
  });
});
