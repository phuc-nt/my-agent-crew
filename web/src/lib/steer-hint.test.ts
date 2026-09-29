import { describe, expect, it } from "vitest";
import type { CommandInfo } from "../api/types";
import { steerHint } from "./steer-hint";

const commands: CommandInfo[] = [{ name: "review", description: "", path: "" }];

describe("steerHint", () => {
  it.each([
    ["/tmp/x", "queue"],
    ["/Users/a/b", "queue"],
    ["/unknown-command", "queue"],
    ["/steer", "steer"],
    ["/steer x", "steer"],
    ["/review src/x.py", "steer"],
    ["chỉ là chữ thường", "queue"],
  ] as const)("%s -> %s", (text, expected) => {
    expect(steerHint(text, commands)).toBe(expected);
  });
});
