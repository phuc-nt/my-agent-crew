import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AgentAvatar, agentHue, initial } from "./agent-avatar";
import { BrandMark } from "./brand-mark";

describe("AgentAvatar", () => {
  it("gives an agent the same hue every time, from the palette's range", () => {
    for (const id of ["default", "coach", "ledger", "kongming", ""]) {
      expect(agentHue(id)).toBe(agentHue(id));
      expect(agentHue(id)).toBeGreaterThanOrEqual(1);
      expect(agentHue(id)).toBeLessThanOrEqual(8);
    }
    expect(new Set(["default", "coach", "ledger", "kongming"].map(agentHue)).size).toBeGreaterThan(1);
  });

  it("takes the first letter a person would say, capitalised the Vietnamese way", () => {
    expect(initial("trợ lý")).toBe("T");
    expect(initial("đội trưởng")).toBe("Đ");
    expect(initial("  🤖 ledger")).toBe("L");
    expect(initial("2nd")).toBe("2");
    expect(initial("—")).toBe("?");
  });

  it("stays out of the text and the accessibility tree of the row it sits in", () => {
    const { container } = render(<AgentAvatar id="coach" name="Huấn luyện viên" />);
    const avatar = container.querySelector(".avatar");
    expect(avatar).toHaveAttribute("aria-hidden", "true");
    expect(avatar).toHaveAttribute("data-initial", "H");
    expect(avatar).toHaveTextContent("");
  });
});

describe("BrandMark", () => {
  // A shared gradient id resolves to the first copy in the page; when that copy is in the
  // closed phone drawer, every other mark loses its fill.
  it("gives every copy its own gradient", () => {
    const { container } = render(
      <>
        <BrandMark />
        <BrandMark />
      </>,
    );
    const ids = [...container.querySelectorAll("linearGradient")].map((g) => g.id);
    expect(ids).toHaveLength(2);
    expect(new Set(ids).size).toBe(2);
    container.querySelectorAll("rect").forEach((rect, i) => {
      expect(rect).toHaveAttribute("fill", `url(#${ids[i]})`);
    });
  });
});
