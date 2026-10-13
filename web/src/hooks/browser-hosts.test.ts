import { describe, expect, it } from "vitest";
import { badHost, hostLines } from "./browser-hosts";

describe("the list a box of host lines stands for", () => {
  it("is one host per line, in the order typed", () => {
    expect(hostLines("shop.example\n*.bank.example\nlocalhost")).toEqual(["shop.example", "*.bank.example", "localhost"]);
  });

  it("drops the space around a line and the lines left blank", () => {
    expect(hostLines("  shop.example \n\n   \n\t*.bank.example\n")).toEqual(["shop.example", "*.bank.example"]);
  });

  it("writes a name small: a capital means the same host, and the server takes lower case only", () => {
    expect(hostLines("Shop.Example\nWWW.BANK.EXAMPLE")).toEqual(["shop.example", "www.bank.example"]);
  });

  it("is empty for a box with nothing in it", () => {
    expect(hostLines("")).toEqual([]);
    expect(hostLines("\n \n")).toEqual([]);
  });

  it("keeps a line that is no host name as typed, for the check to name", () => {
    expect(hostLines("https://Shop.example/cart")).toEqual(["https://shop.example/cart"]);
  });
});

describe("the first host the server would refuse", () => {
  it.each([
    "shop.example",
    "*.shop.example",
    "localhost",
    "127.0.0.1",
    "my-shop.example",
    "xn--80ak6aa92e.example",
    "a.b.c.d.example",
    "*.localhost",
  ])("takes %s", (host) => {
    expect(badHost([host])).toBeUndefined();
  });

  it.each([
    ["a scheme", "https://shop.example"],
    ["a port", "shop.example:8443"],
    ["a path", "shop.example/cart"],
    ["a trailing slash", "shop.example/"],
    ["a star with no name", "*."],
    ["a star with no dot", "*shop.example"],
    ["a star alone", "*"],
    ["a star inside the name", "shop.*.example"],
    ["two stars", "*.*.example"],
    ["two dots in a row", "shop..example"],
    ["a dot in front", ".shop.example"],
    ["a dot at the end", "shop.example."],
    ["a space inside", "shop example"],
    ["an underscore", "my_shop.example"],
    ["a capital", "Shop.example"],
    ["a query", "shop.example?x=1"],
    ["a user", "me@shop.example"],
  ])("refuses %s", (_what, host) => {
    expect(badHost([host])).toBe(host);
  });

  it("names the first of several, not the last", () => {
    expect(badHost(["shop.example", "https://a.example", "b.example:80"])).toBe("https://a.example");
  });

  it("finds nothing in a list of good names, nor in none", () => {
    expect(badHost(["shop.example", "*.bank.example"])).toBeUndefined();
    expect(badHost([])).toBeUndefined();
  });

  it("takes every line the box turns into a host, and refuses a pasted address whole", () => {
    expect(badHost(hostLines(" Shop.Example \n\n*.Bank.example"))).toBeUndefined();
    expect(badHost(hostLines("shop.example\nhttps://Shop.example:8443/cart"))).toBe("https://shop.example:8443/cart");
  });
});
