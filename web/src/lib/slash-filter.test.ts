import { describe, expect, it } from "vitest";
import type { CommandInfo } from "../api/types";
import { filterCommands, insertCommand, slashQuery } from "./slash-filter";

const command = (name: string): CommandInfo => ({ name, description: "", path: `/kit/commands/${name}.md` });
const names = (list: CommandInfo[]) => list.map((c) => c.name);

// The agent's own order, which each tier keeps.
const commands = ["tong-ket", "plan", "review", "đọc-sách", "preview", "ak:plan"].map(command);

describe("slashQuery", () => {
  it("reads the name being typed only while the box is a '/' and one word", () => {
    expect(slashQuery("/")).toBe("");
    expect(slashQuery("/rev")).toBe("rev");
    expect(slashQuery("/ak:plan")).toBe("ak:plan");
  });

  it("is not a command once it has arguments, starts later, or is not a '/' at all", () => {
    expect(slashQuery("/review src/x.py")).toBeNull();
    expect(slashQuery("/review ")).toBeNull();
    expect(slashQuery("đi /home")).toBeNull();
    expect(slashQuery(" /review")).toBeNull();
    expect(slashQuery("")).toBeNull();
  });
});

describe("filterCommands", () => {
  it("shows every command, in the agent's order, before anything is typed", () => {
    expect(names(filterCommands(commands, ""))).toEqual(names(commands));
  });

  it("puts names that start with what was typed before names that only contain it", () => {
    // "plan" and "preview" start with "p"; "ak:plan" only contains it.
    expect(names(filterCommands(commands, "p"))).toEqual(["plan", "preview", "ak:plan"]);
    expect(names(filterCommands(commands, "plan"))).toEqual(["plan", "ak:plan"]);
    expect(names(filterCommands(commands, "view"))).toEqual(["review", "preview"]);
  });

  it("ignores case and accents, and treats đ as the d a hurried person types", () => {
    expect(names(filterCommands(commands, "doc"))).toEqual(["đọc-sách"]);
    expect(names(filterCommands(commands, "ĐỌC"))).toEqual(["đọc-sách"]);
    expect(names(filterCommands(commands, "REV"))).toEqual(["review", "preview"]);
  });

  it("finds nothing when no name holds what was typed", () => {
    expect(filterCommands(commands, "xyz")).toEqual([]);
  });
});

describe("insertCommand", () => {
  it("replaces the name being typed with the whole name and a space, the way the server expands it", () => {
    expect(insertCommand("/rev", "review", commands)).toBe("/review ");
    expect(insertCommand("/", "plan", commands)).toBe("/plan ");
  });

  it("keeps text written before the pick as the command's arguments", () => {
    expect(insertCommand("src/x.py", "review", commands)).toBe("/review src/x.py");
    expect(insertCommand("/review src/x.py", "plan", commands)).toBe("/plan src/x.py");
  });

  it("keeps a path that only starts with '/' whole instead of taking it for a command", () => {
    expect(insertCommand("/Users/me/a.txt đọc giúp", "review", commands)).toBe("/review /Users/me/a.txt đọc giúp");
  });
});
