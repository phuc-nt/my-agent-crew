import { describe, expect, it } from "vitest";
import { parseSource } from "./canvas-source";

describe("where a canvas says it came from", () => {
  it("is a file in an agent's workspace", () => {
    expect(parseSource("workspace:master/thuc-don.md")).toEqual({ kind: "workspace", agentId: "master", path: "thuc-don.md" });
  });

  it("is cut at the first slash, so an agent id may hold a dash and a path any slash or colon", () => {
    expect(parseSource("workspace:health-coach/notes/2026/tuần 1: kế hoạch.md")).toEqual({
      kind: "workspace",
      agentId: "health-coach",
      path: "notes/2026/tuần 1: kế hoạch.md",
    });
  });

  it("is no workspace file without an agent or without a path", () => {
    for (const source of ["workspace:", "workspace:master", "workspace:master/", "workspace:/notes/a.md"]) {
      expect(parseSource(source), source).toBeNull();
    }
  });

  it("is a workspace file only when the text opens with the word, not when a link or a sentence holds it", () => {
    expect(parseSource("https://example.com/workspace:master/a.md")).toEqual({
      kind: "url",
      href: "https://example.com/workspace:master/a.md",
      host: "example.com",
    });
    expect(parseSource("xem workspace:master/a.md")).toBeNull();
  });

  it("is a web page, by its address as the browser reads it and the host it leads to", () => {
    expect(parseSource("https://example.com/a/b?c=1#d")).toEqual({
      kind: "url",
      href: "https://example.com/a/b?c=1#d",
      host: "example.com",
    });
    expect(parseSource("http://localhost:8080/trang")).toEqual({
      kind: "url",
      href: "http://localhost:8080/trang",
      host: "localhost:8080",
    });
  });

  it("names the host a link really leads to, not the one written before an @", () => {
    expect(parseSource("https://bank.example@evil.test/login")).toMatchObject({ kind: "url", host: "evil.test" });
  });

  it("gives the link whole, as the host it names is read, so a page cannot resolve it to somewhere else", () => {
    // Written without its slashes, an address is one a page of the same scheme resolves against
    // its own: left as written, the link would lead there while its label names this host.
    expect(parseSource("https:example.com/thuc don")).toEqual({
      kind: "url",
      href: "https://example.com/thuc%20don",
      host: "example.com",
    });
  });

  it("is nothing for a link that is not http or https", () => {
    for (const source of ["javascript:alert(1)", "data:text/html,<p>x</p>", "file:///etc/passwd", "ftp://example.com/a"]) {
      expect(parseSource(source), source).toBeNull();
    }
  });

  it("is nothing for no source and for text that is neither", () => {
    for (const source of ["", "user", "notes/a.md", "//example.com/a", "https://"]) {
      expect(parseSource(source), source).toBeNull();
    }
  });
});
