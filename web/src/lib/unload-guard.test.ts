import { afterEach, describe, expect, it } from "vitest";
import { closePage } from "../test/close-page";
import { guardUnload } from "./unload-guard";

const held: Array<() => void> = [];

afterEach(() => {
  while (held.length > 0) held.pop()?.();
});

const hold = () => {
  const release = guardUnload();
  held.push(release);
  return release;
};

describe("asking before the page closes", () => {
  it("lets the page close without a question while nothing is held", () => {
    expect(closePage().defaultPrevented).toBe(false);
  });

  it("asks while held, the way old engines need a return value to", () => {
    hold();

    const event = closePage();

    expect(event.defaultPrevented).toBe(true);
    expect(event.returnValue).toBe("");
  });

  it("stops asking once released, and releasing twice changes nothing", () => {
    const release = hold();

    release();
    release();

    expect(closePage().defaultPrevented).toBe(false);
  });

  it("keeps asking while another holder remains", () => {
    const first = hold();
    const second = hold();

    first();
    expect(closePage().defaultPrevented).toBe(true);

    second();
    expect(closePage().defaultPrevented).toBe(false);
  });
});
