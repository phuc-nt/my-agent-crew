import { describe, expect, it } from "vitest";

// What every other test takes for granted about the browser it renders in.
describe("the test browser", () => {
  it("has working storage, whatever Node version runs the tests", () => {
    window.localStorage.setItem("probe", "1");
    expect(window.localStorage.getItem("probe")).toBe("1");
  });

  it("starts each test with the storage the one before left emptied", () => {
    expect(window.localStorage.getItem("probe")).toBeNull();
  });
});
