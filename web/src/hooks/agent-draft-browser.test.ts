import { describe, expect, it } from "vitest";
import type { AgentInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { fakeAgent } from "../test/fake-backend";
import { draftProblems, hasProblems, problemsShown, toPatch } from "./agent-draft-checks";
import { EDITABLE, toDraft } from "./agent-draft-shape";

/** The agent as a server older than the browser reports it: with neither key. */
function older(): AgentInfo {
  const { browser: _mode, browser_hosts: _hosts, ...rest } = fakeAgent;
  return rest;
}

describe("the browser keys the form starts from", () => {
  it("are the two the file has", () => {
    const draft = toDraft({ ...fakeAgent, browser: "act", browser_hosts: ["shop.example", "*.bank.example"] });

    expect(draft.browser).toBe("act");
    expect(draft.browser_hosts).toEqual(["shop.example", "*.bank.example"]);
  });

  it("read an agent that reports a level and no list as one with no host", () => {
    const { browser_hosts: _hosts, ...agent } = { ...fakeAgent, browser: "read" as const };

    expect(toDraft(agent)).toMatchObject({ browser: "read", browser_hosts: [] });
  });

  it("are neither of them for a server that knows no browser, which would refuse one sent to it", () => {
    const draft = toDraft(older());

    expect(draft).not.toHaveProperty("browser");
    expect(draft).not.toHaveProperty("browser_hosts");
  });

  it("are both among the keys a save may send", () => {
    expect(EDITABLE).toContain("browser");
    expect(EDITABLE).toContain("browser_hosts");
  });
});

describe("a host line the save is held for", () => {
  it("is named in the server's terms, with what to take off it", () => {
    const problems = draftProblems({ browser_hosts: ["shop.example", "https://shop.example/cart"] }, ["browser_hosts"]);

    expect(problems).toEqual({ browserHosts: vi.browser.hostInvalid("https://shop.example/cart") });
    expect(problems.browserHosts).toBe("«https://shop.example/cart» không phải tên máy chủ: bỏ https://, cổng và đường dẫn.");
    // Named at once, not only after a save is tried: the line is wrong, not unfilled.
    expect(problemsShown(problems)).toBe(true);
    expect(hasProblems(problems)).toBe(true);
  });

  it("is the first of several", () => {
    const problems = draftProblems({ browser_hosts: ["a.example:80", "b.example/x"] }, ["browser_hosts"]);

    expect(problems.browserHosts).toBe(vi.browser.hostInvalid("a.example:80"));
  });

  it("is nothing for a list of names the server takes, or for an emptied one", () => {
    expect(draftProblems({ browser_hosts: ["shop.example", "*.bank.example"] }, ["browser_hosts"])).toEqual({});
    expect(draftProblems({ browser_hosts: [] }, ["browser_hosts"])).toEqual({});
  });

  // A file edited by hand may hold a line this form would not have let through. Only a
  // change to the list brings the check, so a save of something else is not held for it.
  it("is not looked for while the list is as the file has it", () => {
    const draft = { browser: "act" as const, browser_hosts: ["https://shop.example"] };

    expect(draftProblems(draft, ["browser"])).toEqual({});
    expect(draftProblems(draft, [])).toEqual({});
  });
});

describe("what a save of the browser keys sends", () => {
  const draft = { ...toDraft(fakeAgent), browser: "read" as const, browser_hosts: ["shop.example"] };

  it("is the level alone when only the level changed", () => {
    expect(toPatch(draft, ["browser"])).toEqual({ browser: "read" });
  });

  it("is the list alone when only the list changed", () => {
    expect(toPatch(draft, ["browser_hosts"])).toEqual({ browser_hosts: ["shop.example"] });
  });

  it("is both when both changed, and nothing of either when neither did", () => {
    expect(toPatch(draft, ["browser", "browser_hosts"])).toEqual({ browser: "read", browser_hosts: ["shop.example"] });
    expect(toPatch(draft, ["name"])).toEqual({ name: fakeAgent.name });
  });

  it("is an empty list for one that was emptied, which the server reads as no list", () => {
    expect(toPatch({ ...draft, browser_hosts: [] }, ["browser_hosts"])).toEqual({ browser_hosts: [] });
  });
});
