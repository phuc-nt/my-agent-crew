import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import { MarkdownBody } from "./markdown-body";

describe("an agent reply carrying markdown", () => {
  it("shows emphasis as emphasis instead of as asterisks", () => {
    const { container } = render(<MarkdownBody text="**Giấc ngủ** quan trọng" />);
    expect(container.querySelector("strong")?.textContent).toBe("Giấc ngủ");
    expect(container.textContent).not.toContain("**");
  });

  it("turns a dash list into list items", () => {
    render(<MarkdownBody text={"- ngủ sớm\n- dậy đúng giờ"} />);
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "ngủ sớm",
      "dậy đúng giờ",
    ]);
  });

  it("renders a GFM table, which models reach for whenever they compare things", () => {
    const table = "| Ngày | Giờ |\n| --- | --- |\n| T2 | 7 |";
    render(<MarkdownBody text={table} />);
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getAllByRole("columnheader").map((th) => th.textContent)).toEqual(["Ngày", "Giờ"]);
  });

  it("puts a fenced block in a scrollable pre, not in a paragraph", () => {
    const { container } = render(<MarkdownBody text={"```bash\nuv run pytest -q\n```"} />);
    const pre = container.querySelector("pre.md-pre");
    expect(pre?.textContent?.trim()).toBe("uv run pytest -q");
    expect(pre?.querySelector("code")?.className).toContain("language-bash");
  });

  it("keeps a fence with no language a block, not a run of inline code", () => {
    const { container } = render(<MarkdownBody text={"```\nnpm test\nnpm run e2e\n```"} />);
    expect(container.querySelector("pre.md-pre code")?.textContent).toBe("npm test\nnpm run e2e\n");
    expect(container.querySelector("code.md-inline")).toBeNull();
  });

  it("keeps inline code inline so a sentence does not break into a block", () => {
    const { container } = render(<MarkdownBody text="chạy `pytest` trước" />);
    expect(container.querySelector("code.md-inline")?.textContent).toBe("pytest");
    expect(container.querySelector("pre")).toBeNull();
  });

  it("escapes raw HTML: a reply is partly built from pages the agent fetched", () => {
    const { container } = render(
      <MarkdownBody text={'<script>alert(1)</script><b onclick="x">đậm</b>'} />,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toContain("<script>");
  });

  it("refuses a javascript: link rather than rendering a clickable one", () => {
    const { container } = render(<MarkdownBody text="[bấm đi](javascript:alert(1))" />);
    const link = container.querySelector("a");
    expect(link?.getAttribute("href") ?? "").not.toContain("javascript:");
  });

  it("sends an external link away from the conversation", () => {
    const { container } = render(<MarkdownBody text="[tài liệu](https://example.com)" />);
    const link = container.querySelector("a");
    expect(link?.getAttribute("target")).toBe("_blank");
    expect(link?.getAttribute("rel")).toContain("noopener");
  });

  it("renders a half-written emphasis as plain text while the reply is still arriving", () => {
    const { container } = render(<MarkdownBody text="**Giấc ng" />);
    expect(container.querySelector("strong")).toBeNull();
    expect(container.textContent).toContain("Giấc ng");
  });

  it("gives each fenced block a copy of its own that takes the code and nothing else", async () => {
    const writeText = vitest.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    try {
      render(
        <MarkdownBody
          text={"Chạy lệnh này:\n\n```bash\nuv run pytest -q\nnpm test\n```\n\nrồi:\n\n```\nnpm run e2e\n```"}
        />,
      );
      const buttons = screen.getAllByRole("button", { name: vi.copy.code });
      expect(buttons).toHaveLength(2);

      fireEvent.click(buttons[0]);
      await screen.findByRole("button", { name: vi.copy.copied });

      // No prose around it and no newline the fence left behind.
      expect(writeText).toHaveBeenCalledWith("uv run pytest -q\nnpm test");
    } finally {
      Reflect.deleteProperty(navigator, "clipboard");
    }
  });

  it("puts no copy button on inline code", () => {
    render(<MarkdownBody text="chạy `pytest` trước" />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
