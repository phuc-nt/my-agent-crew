import { describe, expect, it } from "vitest";
import { readPartialArgs } from "./partial-json-content";

/** What stands in for half a character that has no other half. */
const LOST = String.fromCharCode(0xfffd);

describe("the arguments of a canvas write, read before they are whole", () => {
  it("reads every text it knows from arguments that are whole", () => {
    const whole = JSON.stringify({ id: "00ff00ff00ff", title: "Kế hoạch", kind: "markdown", content: "# Tuần\n\nViệc một" });
    expect(readPartialArgs(whole)).toEqual({
      id: "00ff00ff00ff",
      title: "Kế hoạch",
      kind: "markdown",
      content: "# Tuần\n\nViệc một",
    });
  });

  it("reads the text of the canvas as far as it has come, cut anywhere", () => {
    const whole = '{"title":"Kế hoạch","content":"Việc một\\nViệc hai"}';
    expect(readPartialArgs(whole.slice(0, whole.indexOf("Việc hai")))).toEqual({ title: "Kế hoạch", content: "Việc một\n" });
    expect(readPartialArgs('{"title":"Kế hoạch","content":"')).toEqual({ title: "Kế hoạch", content: "" });
    expect(readPartialArgs('{"title":"Kế hoạch","content":')).toEqual({ title: "Kế hoạch" });
    expect(readPartialArgs('{"title":"Kế hoạch","cont')).toEqual({ title: "Kế hoạch" });
  });

  it("holds a title, a kind and an id back until each is closed", () => {
    expect(readPartialArgs('{"title":"Kế ho')).toEqual({});
    expect(readPartialArgs('{"kind":"mark')).toEqual({});
    expect(readPartialArgs('{"id":"00ff00ff00f')).toEqual({});
    expect(readPartialArgs('{"id":"00ff00ff00ff","kind":"html","title":"Trang"')).toEqual({
      id: "00ff00ff00ff",
      kind: "html",
      title: "Trang",
    });
  });

  it("reads the keys in whatever order they were written", () => {
    expect(readPartialArgs('{"content":"Việc một","title":"Kế hoạch"}')).toEqual({ title: "Kế hoạch", content: "Việc một" });
    // The text is whole, and the title after it is still being written.
    expect(readPartialArgs('{"content":"Việc một","title":"Kế')).toEqual({ content: "Việc một" });
  });

  it("allows the space JSON allows between its parts", () => {
    expect(readPartialArgs(' {\n  "title" : "Kế hoạch" ,\r\n\t"content" : "Việc')).toEqual({ title: "Kế hoạch", content: "Việc" });
  });

  it("reads each escape JSON has", () => {
    const text = '{"content":"a\\nb\\tc\\rd\\be\\ff\\"g\\\\h\\/i\\u00e9\\u0041"}';
    expect(readPartialArgs(text)).toEqual({ content: 'a\nb\tc\rd\be\ff"g\\h/iéA' });
    expect(readPartialArgs(text).content).toBe(JSON.parse(text).content);
  });

  it("reads a character written as two escapes as the one character", () => {
    expect(readPartialArgs('{"content":"vui \\ud83d\\ude00 quá')).toEqual({ content: "vui 😀 quá" });
    expect(readPartialArgs('{"content":"vui \\uD83D\\uDE00"}')).toEqual({ content: "vui 😀" });
    // The first and the last of the characters written that way: both halves at each end of their range.
    expect(readPartialArgs('{"content":"\\ud800\\udc00"}')).toEqual({ content: String.fromCodePoint(0x10000) });
    expect(readPartialArgs('{"content":"\\udbff\\udfff"}')).toEqual({ content: String.fromCodePoint(0x10ffff) });
  });

  it("drops an escape the cut left unfinished, and reads all that came before it", () => {
    expect(readPartialArgs('{"content":"Việc\\')).toEqual({ content: "Việc" });
    expect(readPartialArgs('{"content":"Việc\\u')).toEqual({ content: "Việc" });
    expect(readPartialArgs('{"content":"Việc\\u12')).toEqual({ content: "Việc" });
    expect(readPartialArgs('{"content":"Việc\\u00e')).toEqual({ content: "Việc" });
    // Half of a character written as two escapes is no character yet.
    expect(readPartialArgs('{"content":"vui \\ud83d')).toEqual({ content: "vui " });
    expect(readPartialArgs('{"content":"vui \\ud83d\\')).toEqual({ content: "vui " });
    expect(readPartialArgs('{"content":"vui \\ud83d\\ude0')).toEqual({ content: "vui " });
  });

  it("keeps a half character that will never be made whole from the text, and reads on", () => {
    // The first half with no second after it, and a second half standing alone.
    expect(readPartialArgs('{"content":"a\\ud83db"}')).toEqual({ content: `a${LOST}b` });
    expect(readPartialArgs('{"content":"a\\ud83d\\u0041b"}')).toEqual({ content: `a${LOST}Ab` });
    expect(readPartialArgs('{"content":"a\\ude00b"}')).toEqual({ content: `a${LOST}b` });
    expect(readPartialArgs('{"content":"a\\ud83d\\nb"}')).toEqual({ content: `a${LOST}\nb` });
    // What follows the first half only looks like the end of an escape: no backslash opens it.
    expect(readPartialArgs('{"content":"a\\ud83dxude00b"}')).toEqual({ content: `a${LOST}xude00b` });
  });

  it("reads past an escape that is no escape of JSON without losing the rest", () => {
    expect(readPartialArgs('{"content":"a\\qb","title":"T"}')).toEqual({ content: "aqb", title: "T" });
    // The four that should be digits may hold the end of the text, so only the escape itself goes.
    expect(readPartialArgs('{"content":"a\\uzzzzb"}')).toEqual({ content: `a${LOST}zzzzb` });
    expect(readPartialArgs('{"content":"a\\u12","title":"T"}')).toEqual({ content: `a${LOST}12`, title: "T" });
  });

  it("passes over every value that is not text, whatever it holds", () => {
    const text =
      '{"n":-12.5e3,"t":true,"f":false,"z":null,"list":[1,"]",{"content":"trong mảng"},[2]],' +
      '"nested":{"content":"lồng","deep":{"title":"sâu"},"s":"}"},"content":"thật"}';
    expect(readPartialArgs(text)).toEqual({ content: "thật" });
    // A quote written inside a text does not end it, and a backslash written there does not hide the quote that does.
    expect(readPartialArgs('{"nested":{"s":"a\\"}"},"content":"x"}')).toEqual({ content: "x" });
    expect(readPartialArgs('{"nested":{"s":"a\\\\"},"content":"x"}')).toEqual({ content: "x" });
    expect(readPartialArgs('{"list":["a\\"]","[",{"k":"]}"}],"content":"x"}')).toEqual({ content: "x" });
  });

  it("takes no text for a key from a value that is not text", () => {
    expect(readPartialArgs('{"title":7,"kind":["markdown"],"id":{"id":"00ff00ff00ff"},"content":null}')).toEqual({});
    expect(readPartialArgs('{"content":{"content":"lồng"},"title":"T"}')).toEqual({ title: "T" });
  });

  it("stops at a value that is not text and is not whole yet", () => {
    expect(readPartialArgs('{"title":"T","list":[1,{"content":"trong')).toEqual({ title: "T" });
    expect(readPartialArgs('{"title":"T","nested":{"content":"lồng"')).toEqual({ title: "T" });
    expect(readPartialArgs('{"title":"T","n":12')).toEqual({ title: "T" });
  });

  it("does not take a key's name for the key when it stands as a value, or inside a text", () => {
    expect(readPartialArgs('{"note":"content","content":"thật"}')).toEqual({ content: "thật" });
    expect(readPartialArgs('{"note":"\\"content\\":\\"giả\\"","title":"T"}')).toEqual({ title: "T" });
  });

  it("takes the last text a key was given when the key comes twice, as the server will", () => {
    expect(readPartialArgs('{"content":"một","content":"hai"}')).toEqual({ content: "hai" });
    expect(readPartialArgs('{"title":"A","title":"B"}')).toEqual({ title: "B" });
    // The second is not closed yet, so the first still stands.
    expect(readPartialArgs('{"title":"A","title":"B')).toEqual({ title: "A" });
  });

  it("reads no key it does not know, the language of a code canvas included", () => {
    expect(readPartialArgs('{"language":"python","old":"a","new":"b","content":"x"}')).toEqual({ content: "x" });
    expect(readPartialArgs('{"toString":"a","__proto__":"b","constructor":"c"}')).toEqual({});
  });

  it("reads nothing from what is not an object", () => {
    for (const text of ["", "   ", "rác", '"content"', '["content"]', "nul", "12", '"{\\"content\\":\\"x\\"}"']) {
      expect(readPartialArgs(text)).toEqual({});
    }
    // What stands first is no opening brace, though a key and its text follow as they would in an object.
    expect(readPartialArgs('["content":"x"]')).toEqual({});
    expect(readPartialArgs('x"content":"y"')).toEqual({});
  });

  it("reads what it can from an object that goes wrong, and nothing after the place it does", () => {
    expect(readPartialArgs("{")).toEqual({});
    expect(readPartialArgs('{"title":"T" "content":"x"}')).toEqual({ title: "T" });
    expect(readPartialArgs('{"title":"T",,"content":"x"}')).toEqual({ title: "T" });
    expect(readPartialArgs('{title:"T","content":"x"}')).toEqual({});
    expect(readPartialArgs('{"title":"T","n":,"content":"x"}')).toEqual({ title: "T" });
    expect(readPartialArgs('{"title":"T","n":true false,"content":"x"}')).toEqual({ title: "T" });
    expect(readPartialArgs('{"title" "T","content":"x"}')).toEqual({});
    // Another mark where the colon or the comma belongs is not that colon or comma.
    expect(readPartialArgs('{"title"="T"}')).toEqual({});
    expect(readPartialArgs('{"title":"T";"content":"x"}')).toEqual({ title: "T" });
    // Nothing is read past the end of the object.
    expect(readPartialArgs('{"title":"T"}{"content":"x"}')).toEqual({ title: "T" });
    expect(readPartialArgs('{"title":"T"},"content":"x"')).toEqual({ title: "T" });
  });

  it("reads a text of a megabyte in one pass, as it does a short one", () => {
    const body = "dòng chữ dài\\n".repeat(80_000);
    const read = readPartialArgs(`{"title":"Lớn","content":"${body}`);
    expect(read.title).toBe("Lớn");
    expect(read.content).toBe("dòng chữ dài\n".repeat(80_000));
  });
});
