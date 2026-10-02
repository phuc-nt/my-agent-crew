import { describe, expect, it } from "vitest";
import { formatBytes } from "./format-bytes";

describe("a size as people read it", () => {
  it("counts bytes below a kilobyte one by one", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(812)).toBe("812 B");
    expect(formatBytes(1023)).toBe("1023 B");
  });

  it("steps up by 1024 and drops a decimal that is zero", () => {
    expect(formatBytes(1024)).toBe("1 KB");
    expect(formatBytes(1048576)).toBe("1 MB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5 MB");
    expect(formatBytes(1024 ** 3)).toBe("1 GB");
  });

  it("writes one decimal under ten with a comma, as Vietnamese does", () => {
    expect(formatBytes(1536)).toBe("1,5 KB");
    expect(formatBytes(1.2 * 1024 * 1024)).toBe("1,2 MB");
  });

  it("writes whole numbers from ten up", () => {
    expect(formatBytes(432 * 1024)).toBe("432 KB");
    expect(formatBytes(512 * 1024)).toBe("512 KB");
  });

  it("moves up a unit when rounding would reach 1024 of the one below", () => {
    expect(formatBytes(1024 * 1024 - 1)).toBe("1 MB");
    expect(formatBytes(9.97 * 1024)).toBe("10 KB");
  });
});
