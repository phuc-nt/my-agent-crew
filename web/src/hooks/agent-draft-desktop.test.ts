// The desktop's two keys as the agent form holds them and a save sends them. A server older
// than the desktop reports neither and would refuse one sent to it; the form then holds
// neither, so no diff can ever carry one.
import { describe, expect, it } from "vitest";
import { fakeAgent } from "../test/fake-backend";
import { toPatch } from "./agent-draft-checks";
import { EDITABLE, toDraft } from "./agent-draft-shape";

describe("the desktop keys the form starts from", () => {
  it("are the two the file has", () => {
    const draft = toDraft({ ...fakeAgent, computer: "on", computer_apps: ["Notes", "com.apple.Safari"] });

    expect(draft.computer).toBe("on");
    expect(draft.computer_apps).toEqual(["Notes", "com.apple.Safari"]);
  });

  it("read an agent that reports a mode and no list as one that only looks", () => {
    expect(toDraft({ ...fakeAgent, computer: "on" })).toMatchObject({ computer: "on", computer_apps: [] });
  });

  it("are neither of them for a server that knows no desktop, which would refuse one sent to it", () => {
    expect(fakeAgent).not.toHaveProperty("computer");
    const draft = toDraft(fakeAgent);

    expect(draft).not.toHaveProperty("computer");
    expect(draft).not.toHaveProperty("computer_apps");
  });

  it("are both among the keys a save may send", () => {
    expect(EDITABLE).toContain("computer");
    expect(EDITABLE).toContain("computer_apps");
  });
});

describe("what a save of the desktop keys sends", () => {
  const draft = { ...toDraft({ ...fakeAgent, computer: "off", computer_apps: [] }), computer: "on" as const, computer_apps: ["Notes"] };

  it("is the mode alone, as the word, when only the mode changed", () => {
    expect(toPatch(draft, ["computer"])).toEqual({ computer: "on" });
  });

  it("is the list alone when only the list changed, and an empty list for one emptied", () => {
    expect(toPatch(draft, ["computer_apps"])).toEqual({ computer_apps: ["Notes"] });
    expect(toPatch({ ...draft, computer_apps: [] }, ["computer_apps"])).toEqual({ computer_apps: [] });
  });
});
