import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

describe("an image in a reply", () => {
  it("holds back an image from another site until asked, then loads it without a referrer", async () => {
    render(<MarkdownBody text="Xem ![biểu đồ giấc ngủ](https://tracker.example/pixel.png) nhé" />);
    expect(screen.queryByRole("img")).toBeNull();
    const offer = screen.getByRole("button", { name: `${vi.markdownImage.show("tracker.example")} biểu đồ giấc ngủ` });

    fireEvent.click(offer);
    const image = screen.getByRole("img", { name: "biểu đồ giấc ngủ" });
    expect(image).toHaveAttribute("src", "https://tracker.example/pixel.png");
    expect(image).toHaveAttribute("referrerpolicy", "no-referrer");
    // The button it replaced held the focus; the image takes it rather than the page.
    await waitFor(() => expect(image).toHaveFocus());
  });

  it("shows the app's own images at once", () => {
    const own = `${window.location.origin}/api/agents/coach/files/chart.png`;
    render(<MarkdownBody text={`![của mình](${own}) ![tương đối](/files/a.png)`} />);
    expect(screen.getAllByRole("img").map((img) => img.getAttribute("alt"))).toEqual(["của mình", "tương đối"]);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("holds back a remote image in a wiki page too", () => {
    render(<MarkdownBody text="![ảnh](http://elsewhere.test/a.png)" wikiLink={(slug) => slug} />);
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByRole("button", { name: vi.markdownImage.show("elsewhere.test") + " ảnh" })).toBeInTheDocument();
  });

  // A page is drawn again as it is written or edited, and the image at one place in it may by
  // then come from another address. The yes a person gave was to the address they were shown.
  const FIRST = "https://tracker.example/a.png";
  const offer = (host: string, alt: string) => screen.getByRole("button", { name: `${vi.markdownImage.show(host)} ${alt}` });
  const drawn = (src: string) => document.querySelector(`img[src="${src}"]`);

  it("asks again when the image it showed gives way to one at another address", () => {
    const { rerender } = render(<MarkdownBody text={`![biểu đồ](${FIRST})`} />);
    fireEvent.click(offer("tracker.example", "biểu đồ"));
    expect(drawn(FIRST)).toBeInTheDocument();

    // The same site, and still not the address that was agreed to.
    const next = "https://tracker.example/b.png?id=7";
    rerender(<MarkdownBody text={`![biểu đồ](${next})`} />);
    expect(screen.queryByRole("img")).toBeNull();
    expect(drawn(next)).toBeNull();
    expect(offer("tracker.example", "biểu đồ")).toHaveAttribute("title", next);

    fireEvent.click(offer("tracker.example", "biểu đồ"));
    expect(screen.getByRole("img", { name: "biểu đồ" })).toHaveAttribute("src", next);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows an image again unasked when the page comes back to the address agreed to, and takes no focus for it", () => {
    const page = (src: string) => (
      <>
        <input aria-label="ô soạn" />
        <MarkdownBody text={`![biểu đồ](${src})`} />
      </>
    );
    const { rerender } = render(page(FIRST));
    fireEvent.click(offer("tracker.example", "biểu đồ"));

    const other = "https://elsewhere.test/a.png";
    rerender(page(other));
    expect(drawn(other)).toBeNull();
    expect(offer("elsewhere.test", "biểu đồ")).toHaveAttribute("title", other);
    const box = screen.getByRole("textbox", { name: "ô soạn" });
    box.focus();
    expect(box).toHaveFocus();

    // The person said yes to this very address and it was fetched then: asking a second time
    // would keep nothing from whoever serves it. No button was pressed now, so the focus stays
    // where the person has it.
    rerender(page(FIRST));
    expect(screen.getByRole("img", { name: "biểu đồ" })).toHaveAttribute("src", FIRST);
    expect(screen.queryByRole("button")).toBeNull();
    expect(box).toHaveFocus();
  });

  it("never holds the app's own image, and showing one agrees to nothing from outside", () => {
    const own = `${window.location.origin}/api/agents/coach/files/chart.png`;
    const { rerender } = render(<MarkdownBody text={`![ảnh](${FIRST})`} />);
    fireEvent.click(offer("tracker.example", "ảnh"));

    for (const mine of [own, "/files/a.png"]) {
      rerender(<MarkdownBody text={`![ảnh](${mine})`} />);
      expect(screen.getByRole("img", { name: "ảnh" })).toHaveAttribute("src", mine);
      expect(screen.queryByRole("button")).toBeNull();
    }

    const outside = "https://elsewhere.test/pixel.png";
    rerender(<MarkdownBody text={`![ảnh](${outside})`} />);
    expect(drawn(outside)).toBeNull();
    expect(offer("elsewhere.test", "ảnh")).toHaveAttribute("title", outside);
  });

  it("asks about each image of a page on its own", () => {
    const second = "https://tracker.example/b.png";
    const page = (one: string, two: string) => `![một](${one})\n\n![hai](${two})`;
    const { rerender } = render(<MarkdownBody text={page(FIRST, second)} />);
    expect(screen.queryByRole("img")).toBeNull();

    // A yes to one image of a site is no yes to the next one from it.
    fireEvent.click(offer("tracker.example", "một"));
    expect(screen.getAllByRole("img").map((img) => img.getAttribute("src"))).toEqual([FIRST]);
    expect(offer("tracker.example", "hai")).toHaveAttribute("title", second);

    fireEvent.click(offer("tracker.example", "hai"));
    expect(screen.getAllByRole("img").map((img) => img.getAttribute("src"))).toEqual([FIRST, second]);

    // One of the two changes its address: that one asks again, and the other stays as it is.
    const third = "https://tracker.example/c.png";
    rerender(<MarkdownBody text={page(FIRST, third)} />);
    expect(screen.getAllByRole("img").map((img) => img.getAttribute("src"))).toEqual([FIRST]);
    expect(drawn(third)).toBeNull();
    expect(offer("tracker.example", "hai")).toHaveAttribute("title", third);
  });
});

describe("the source lines a canvas needs to place a selection", () => {
  const DOC = "para **b**\n\n- a\n- b\n\n> quote\n\n| A |\n| - |\n| 1 |";
  const PLAIN =
    '<div class="md"><p>para <strong>b</strong></p>\n<ul>\n<li>a</li>\n<li>b</li>\n</ul>\n<blockquote>\n<p>quote</p>\n</blockquote>\n<table><thead><tr><th>A</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table></div>';

  it("marks blocks with the lines they were written on when asked", () => {
    const { container } = render(<MarkdownBody text={DOC} sourceLines />);
    const lines = (selector: string) =>
      [...container.querySelectorAll(selector)].map((el) => `${el.getAttribute("data-line-start")}-${el.getAttribute("data-line-end")}`);
    expect(lines("p")).toEqual(["1-1", "6-6"]);
    expect(lines("li")).toEqual(["3-3", "4-4"]);
    expect(lines("blockquote")).toEqual(["6-6"]);
    expect(lines("table")).toEqual(["8-10"]);
    expect(lines("tr")).toEqual(["8-8", "10-10"]);
  });

  it("puts the lines of a fenced block on its code, which is what the page keeps of the block", () => {
    const { container } = render(<MarkdownBody text={"before\n\n```bash\nls\npwd\n```"} sourceLines />);
    const code = container.querySelector("pre.md-pre code");
    expect(code).toHaveAttribute("data-line-start", "3");
    expect(code).toHaveAttribute("data-line-end", "6");
    expect(container.querySelector("pre")).not.toHaveAttribute("data-line-start");
  });

  it("leaves code inside a sentence without lines", () => {
    const { container } = render(<MarkdownBody text="chạy `pytest` trước" sourceLines />);
    expect(container.querySelector("code.md-inline")).not.toHaveAttribute("data-line-start");
  });

  it("draws exactly the HTML it drew before when not asked", () => {
    const { container } = render(<MarkdownBody text={DOC} />);
    expect(container.innerHTML).toBe(PLAIN);
    expect(container.querySelector("[data-line-start]")).toBeNull();
  });

  it("does not let the text forge lines: markup in it stays text", () => {
    const { container } = render(
      <MarkdownBody text={'<p data-line-start="9" data-line-end="9">x</p>\n\nreal'} sourceLines />,
    );
    expect([...container.querySelectorAll("[data-line-start]")].map((el) => el.getAttribute("data-line-start"))).toEqual(["3"]);
    expect(container.textContent).toContain('data-line-start="9"');
  });
});
