import { describe, expect, it } from "vitest";
import { prettyJson } from "./pretty-json";

describe("JSON text set out to be read", () => {
  it("puts each member on a line of its own, two spaces in for each level", () => {
    expect(prettyJson('{"seen":["a1","b2"],"count":2,"last":{"ok":true,"at":null}}')).toBe(
      [
        "{",
        '  "seen": [',
        '    "a1",',
        '    "b2"',
        "  ],",
        '  "count": 2,',
        '  "last": {',
        '    "ok": true,',
        '    "at": null',
        "  }",
        "}",
      ].join("\n"),
    );
  });

  it("reads as the same value it was", () => {
    const text = '{"a":[1,[2,{"b":"c"}],[]],"d":{},"e":"x\\ny","f":-1.5e3,"g":false}';
    expect(JSON.parse(prettyJson(text) as string)).toEqual(JSON.parse(text));
  });

  it("keeps an empty list and an empty object on one line", () => {
    expect(prettyJson('{"none":[],"nothing":{}}')).toBe('{\n  "none": [],\n  "nothing": {}\n}');
    expect(prettyJson("[]")).toBe("[]");
    expect(prettyJson("{ }")).toBe("{}");
  });

  // Parsing and printing again would hand back 12345678901234567000 and 1.1.
  it("copies each number as it is written, however wide or however it ends", () => {
    expect(prettyJson('{"id":12345678901234567890,"price":1.10,"big":1E400}')).toBe(
      '{\n  "id": 12345678901234567890,\n  "price": 1.10,\n  "big": 1E400\n}',
    );
  });

  it("leaves what a string holds alone: brackets, commas, colons, quotes and escapes", () => {
    const text = String.raw`{"k":"a{b}[c],d:e \"q\" \\","u":"\u00e9 đơn"}`;
    expect(prettyJson(text)).toBe(String.raw`{
  "k": "a{b}[c],d:e \"q\" \\",
  "u": "\u00e9 đơn"
}`);
  });

  it("spaces a text that came with spaces of its own the same way", () => {
    expect(prettyJson(' {\n"a" :\t1 ,\r\n"b":[ 2 , 3 ] }\n')).toBe('{\n  "a": 1,\n  "b": [\n    2,\n    3\n  ]\n}');
  });

  it("gives a value that is not a list or an object as it stands", () => {
    expect(prettyJson('"chỉ một chuỗi"')).toBe('"chỉ một chuỗi"');
    expect(prettyJson("42")).toBe("42");
    expect(prettyJson("null")).toBe("null");
    expect(prettyJson(" true ")).toBe("true");
  });
});

describe("a text that is not JSON", () => {
  it.each([
    ["nothing at all", ""],
    ["plain words", "đơn hàng mới"],
    ["a key without quotes", "{a:1}"],
    ["a comma too many", "[1,2,]"],
    ["an object cut short", '{"a":1'],
    ["a string cut short", '{"a":"b'],
    ["a number no JSON holds", "NaN"],
    ["two values", "1 2"],
  ])("has no setting-out: %s", (_, text) => {
    expect(prettyJson(text)).toBeNull();
  });
});
