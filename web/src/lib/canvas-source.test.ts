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

  it("is no link when the address names who logs in there, by a name, a password or both", () => {
    // What stands before the @ would lead the address a browser shows, and a password would sit in the page.
    const sources = [
      "https://bank.example@evil.test/login",
      "https://ai:matkhau@example.com/a",
      "https://:matkhau@example.com/a",
      "https://ai:@example.com/a",
      "http://example.com%40ai@khac.example/",
    ];
    for (const source of sources) expect(parseSource(source), source).toBeNull();
  });

  it("links an address whose login is empty as the browser reads it: no @ is left in it", () => {
    for (const source of ["https://@example.com/a", "https://:@example.com/a"]) {
      expect(parseSource(source), source).toEqual({ kind: "url", href: "https://example.com/a", host: "example.com" });
    }
  });

  it("keeps an @ that sits in the path, the query or the fragment", () => {
    for (const source of ["https://medium.com/@tac-gia/bai-viet", "https://example.com/tim?q=ai@example.vn#muc@2"]) {
      expect(parseSource(source), source).toMatchObject({ kind: "url", href: source });
    }
  });

  it("is no link when the host holds a character that would read as part of the words around it", () => {
    // Each is a host the browser's own parser takes, and the label draws the host inside brackets.
    const hosts = ["good.example).evil.test", "a(b.example", "a,b.example", "a;b.example", "a'b.example", "a!b.example"];
    const more = ["a*b.example", "a+b.example", "a$b.example", "a&b.example", "a=b.example", "a~b.example", 'a"b.example', "a`b.example", "a{b}.example"];
    for (const host of [...hosts, ...more]) {
      expect(new URL(`http://${host}/`).host, host).toBe(host);
      expect(parseSource(`http://${host}/`), host).toBeNull();
      expect(parseSource(`https://${host}:8443/a?b=1`), host).toBeNull();
    }
  });

  it("links a host written in letters, digits, dots, dashes and underscores, with or without a port", () => {
    const hosts = ["example.com", "tin-tuc.example.com:8443", "my_may.local", "192.168.1.10", "192.168.1.10:8080", "example.com."];
    for (const host of hosts) {
      expect(parseSource(`https://${host}/a`), host).toEqual({ kind: "url", href: `https://${host}/a`, host });
    }
  });

  it("links a host written in another script by the name the browser turns it into", () => {
    expect(parseSource("https://tiếng-việt.vn/a")).toEqual({
      kind: "url",
      href: "https://xn--ting-vit-e50d7c.vn/a",
      host: "xn--ting-vit-e50d7c.vn",
    });
    expect(parseSource("HTTPS://Example.COM/A")).toMatchObject({ href: "https://example.com/A", host: "example.com" });
  });

  it("links an address given as numbers in brackets, and nothing else in brackets", () => {
    expect(parseSource("http://[2001:db8::1]:8080/a")).toMatchObject({ kind: "url", host: "[2001:db8::1]:8080" });
    expect(parseSource("http://[::ffff:192.168.1.10]/a")).toMatchObject({ kind: "url", host: "[::ffff:c0a8:10a]" });
  });

  it("is no link to the app's own address, where a page an agent wrote would open as the app's", () => {
    const { origin, protocol, host, hostname } = window.location;
    expect(origin).toMatch(/^http:\/\/[a-z.]+:\d+$/);
    for (const source of [origin, `${origin}/api/artifacts/0123456789ab/render`, `${protocol}//${host.toUpperCase()}/#/chat/c1`]) {
      expect(parseSource(source), source).toBeNull();
    }
    // Another port or another scheme is another site, as the browser counts one.
    expect(parseSource(`${protocol}//${hostname}:1/a`)).toMatchObject({ kind: "url", host: `${hostname}:1` });
    expect(parseSource(`https://${host}/a`)).toMatchObject({ kind: "url", host });
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
