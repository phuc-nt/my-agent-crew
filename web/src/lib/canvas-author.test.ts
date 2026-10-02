import { describe, expect, it } from "vitest";
import { authorLabel } from "./canvas-author";

const names: Record<string, string> = { ming: "Ming", user: "Trợ lý tên user" };
/** As the crew names an agent: by its name, or by its id once it is gone. */
const agentName = (id: string) => names[id] ?? id;

describe("who wrote a canvas version", () => {
  it("calls the person 'bạn'", () => {
    expect(authorLabel("user", agentName)).toBe("bạn");
  });

  it("names an agent by its name", () => {
    expect(authorLabel("agent:ming", agentName)).toBe("Ming");
  });

  it("names an agent whose id is 'user' as that agent, never as the person", () => {
    expect(authorLabel("agent:user", agentName)).toBe("Trợ lý tên user");
  });

  it("falls back to the id of an agent that no longer exists", () => {
    expect(authorLabel("agent:retired", agentName)).toBe("retired");
  });

  it("shows any other author as it was stored", () => {
    expect(authorLabel("ming", agentName)).toBe("ming");
  });
});
