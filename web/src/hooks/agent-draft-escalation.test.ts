import { describe, expect, it } from "vitest";
import type { AgentPatch } from "../api/types";
import { vi } from "../i18n/vi";
import { draftProblems, hasProblems, problemsShown, toPatch } from "./agent-draft-checks";

const FLASH = { provider: "openrouter", model: "flash" };
const BIG = { provider: "openrouter", model: "big" };

function draft(over: AgentPatch = {}): AgentPatch {
  return { routes: [FLASH], escalation_route: BIG, ...over };
}

describe("the escalation route the form lets through", () => {
  it("takes a route that is none of the agent's own, and no route at all", () => {
    expect(draftProblems(draft(), ["escalation_route"])).toEqual({});
    expect(draftProblems(draft({ escalation_route: null }), ["escalation_route"])).toEqual({});
    // The same model somewhere else is another way to it.
    const elsewhere = draft({ escalation_route: { provider: "groq", model: "flash" } });
    expect(draftProblems(elsewhere, ["escalation_route"])).toEqual({});
  });

  it("refuses one of the agent's own routes, whichever of the two keys was changed", () => {
    const same = draft({ escalation_route: { provider: "openrouter", model: " flash " } });

    expect(draftProblems(same, ["escalation_route"])).toEqual({ escalationRoute: vi.editor.escalationSameAsRoute });
    expect(draftProblems(same, ["routes"])).toEqual({ escalationRoute: vi.editor.escalationSameAsRoute });
  });

  it("checks against every route of the list, not the first alone", () => {
    const second = draft({ routes: [FLASH, BIG] });

    expect(draftProblems(second, ["routes"]).escalationRoute).toBe(vi.editor.escalationSameAsRoute);
  });

  it("leaves a route a file already holds alone while another key is edited", () => {
    const same = draft({ escalation_route: FLASH, name: "Tên mới" });

    expect(draftProblems(same, ["name"])).toEqual({});
  });

  it("holds the save for a model still blank, and names the box once a save is tried", () => {
    const blank = draft({ escalation_route: { provider: "openrouter", model: "  " } });

    const quiet = draftProblems(blank, ["escalation_route"]);
    expect(quiet).toEqual({ unfilled: true });
    expect(hasProblems(quiet)).toBe(true);
    expect(problemsShown(quiet)).toBe(false);

    const named = draftProblems(blank, ["escalation_route"], {}, true);
    expect(named).toEqual({ escalationRoute: vi.editor.escalationModelMissing });
    expect(problemsShown(named)).toBe(true);
  });
});

describe("the escalation route as it is sent", () => {
  it("goes as a provider and a model, without the space around a pasted name", () => {
    const typed = draft({ escalation_route: { provider: "openrouter", model: " big " } });

    expect(toPatch(typed, ["escalation_route"])).toEqual({ escalation_route: BIG });
  });

  it("goes as null when it was taken away, which clears the key", () => {
    expect(toPatch(draft({ escalation_route: null }), ["escalation_route"])).toEqual({ escalation_route: null });
  });

  it("is left out of an edit that did not touch it", () => {
    expect(toPatch(draft({ name: "Tên mới" }), ["name"])).toEqual({ name: "Tên mới" });
  });
});
