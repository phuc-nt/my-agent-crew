import { readFileSync } from "node:fs";
import type { Route } from "@playwright/test";
import type { FakeCanvas } from "../src/test/fake-canvas";

/**
 * `GET /artifacts/{id}/render` as the server answers it, for a canvas of kind `html`: the canvas's
 * own text as a page, with the reporter put in and the policy on the response. Both come from the
 * two files `tests/test_render_fixtures.py` keeps equal to the server's, so what a browser test
 * sees a page do is what it would do against the server.
 *
 * A Mermaid page loads its library from a CDN, which no browser test reaches: only HTML is served.
 */

const fixture = (name: string) => readFileSync(new URL(name, import.meta.url), "utf8");

/** The `Content-Security-Policy` the render route sends. */
export const RENDER_POLICY = fixture("render-policy.txt");
const REPORTER_TAG = `<script>${fixture("frame-reporter.js")}</script>`;

// As `_DOCTYPE` in `artifacts/render.py`: a doctype that begins the page, after a byte order mark,
// blank space and comments. The pages here are a test's own, so the loop need not be possessive.
const DOCTYPE = /^(?:﻿|[ \t\n\f\r]|<!--[\s\S]*?-->)*<!doctype[^>]*>/i;
const DOCTYPE_WINDOW = 2048;

/** As `html_page` on the server: the reporter right after a leading doctype, else at the very top. */
export function htmlPage(content: string): string {
  const at = DOCTYPE.exec(content.slice(0, DOCTYPE_WINDOW))?.[0].length ?? 0;
  return content.slice(0, at) + REPORTER_TAG + content.slice(at);
}

/** Answers the render route of an HTML canvas; null for any other path, which the caller goes on with. */
export function renderRoute(route: Route, canvas: FakeCanvas, path: string, method: string): Promise<void> | null {
  const id = /^\/artifacts\/([^/]+)\/render$/.exec(path)?.[1];
  if (id === undefined || method !== "GET") return null;
  const found = canvas.canvases.get(decodeURIComponent(id));
  if (found?.summary.kind !== "html") {
    return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not Found" }) });
  }
  return route.fulfill({
    status: 200,
    contentType: "text/html; charset=utf-8",
    headers: {
      "Content-Security-Policy": RENDER_POLICY,
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
      "Cache-Control": "no-store",
    },
    body: htmlPage(canvas.content(found.summary.id) ?? ""),
  });
}
