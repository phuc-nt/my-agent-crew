import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { parseRoute, routeHash, useRoute } from "./use-route";

afterEach(() => {
  window.location.hash = "";
});

describe("reading a route from the address bar", () => {
  it("opens the chat when there is no hash at all", () => {
    expect(parseRoute("")).toEqual({ kind: "chat", conversationId: null });
  });

  it("names the conversation a chat link points at", () => {
    expect(parseRoute("#/chat/abc123")).toEqual({ kind: "chat", conversationId: "abc123" });
  });

  it("reads the section out of a manage link", () => {
    expect(parseRoute("#/manage/jobs")).toEqual({ kind: "manage", section: "jobs" });
  });

  // A link from an older build, or one someone typed by hand, must still land somewhere.
  it("falls back to the first section when the section is not one we have", () => {
    expect(parseRoute("#/manage/nonsense")).toEqual({ kind: "manage", section: "activity" });
  });

  it("falls back to the chat for a hash that means nothing here", () => {
    expect(parseRoute("#/nonsense/deep")).toEqual({ kind: "chat", conversationId: null });
  });

  it("reads what a section is opened on out of the third segment", () => {
    expect(parseRoute("#/manage/crew/default")).toEqual({
      kind: "manage",
      section: "crew",
      param: "default",
    });
    expect(parseRoute("#/manage/activity/run-7")).toEqual({
      kind: "manage",
      section: "activity",
      param: "run-7",
    });
  });

  // An id that needs escaping still has to survive the round trip through the bar.
  it("keeps an id that contains a slash intact", () => {
    const route = { kind: "manage", section: "activity", param: "job/2" } as const;
    expect(parseRoute(routeHash(route))).toEqual(route);
  });

  it("drops the id when the section is not one we have", () => {
    // Landing on the default section still carrying someone else's id would open
    // something nobody asked for.
    expect(parseRoute("#/manage/nonsense/default")).toEqual({
      kind: "manage",
      section: "activity",
    });
  });

  it("writes a hash that reads back as the same route", () => {
    const routes = [
      { kind: "chat", conversationId: null },
      { kind: "chat", conversationId: "c1" },
      { kind: "manage", section: "costs" },
      { kind: "manage", section: "activity", param: "r1" },
    ] as const;

    for (const route of routes) expect(parseRoute(routeHash(route))).toEqual(route);
  });
});

describe("moving between screens", () => {
  it("follows the address bar when the person uses Back", () => {
    const { result } = renderHook(() => useRoute());

    act(() => result.current.navigate({ kind: "manage", section: "crew" }));
    expect(result.current.route).toEqual({ kind: "manage", section: "crew" });

    act(() => result.current.navigate({ kind: "chat", conversationId: "c9" }));
    expect(result.current.route).toEqual({ kind: "chat", conversationId: "c9" });
  });

  // Reflecting a conversation the app chose on its own should not give the person a Back
  // step they never took.
  it("rewrites the address without adding a history entry", () => {
    const { result } = renderHook(() => useRoute());
    const before = window.history.length;

    act(() => result.current.replace({ kind: "chat", conversationId: "auto" }));

    expect(result.current.route).toEqual({ kind: "chat", conversationId: "auto" });
    expect(window.location.hash).toBe("#/chat/auto");
    expect(window.history.length).toBe(before);
  });
});
