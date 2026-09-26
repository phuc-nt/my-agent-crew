import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import { WikiReadView } from "./wiki-read-view";

const titles = new Map([
  ["han-eco", "Hạn Eco"],
  ["tra-sang", "Trà sáng"],
  ["ふびん", "ふびん"],
]);

function mount(body: string) {
  const onOpen = vitest.fn();
  const view = render(<WikiReadView body={body} titles={titles} onOpen={onOpen} />);
  return { onOpen, view };
}

describe("WikiReadView links", () => {
  it("opens the page a [[Name]] slugs to, the way the server files it", async () => {
    const { onOpen } = mount("Xem [[Trà sáng]] và [[ Hạn Eco ]].");

    await userEvent.click(screen.getByRole("button", { name: "Trà sáng" }));
    await userEvent.click(screen.getByRole("button", { name: "Hạn Eco" }));
    expect(onOpen.mock.calls).toEqual([["tra-sang"], ["han-eco"]]);
  });

  it("keeps a title written in another script, which the renderer percent-encodes", async () => {
    const { onOpen } = mount("Nghĩa của [[ふびん]].");

    await userEvent.click(screen.getByRole("button", { name: "ふびん" }));
    expect(onOpen).toHaveBeenCalledWith("ふびん");
  });

  it("leaves brackets inside code alone, since there they are text about links", () => {
    const { view } = mount("Cú pháp là `[[Trà sáng]]`.\n\n```\n[[Hạn Eco]]\n```");

    expect(screen.queryByRole("button")).toBeNull();
    expect(view.container).toHaveTextContent("[[Trà sáng]]");
    expect(view.container).toHaveTextContent("[[Hạn Eco]]");
  });

  it("marks a link to a page that does not exist as missing", () => {
    mount("Hỏi [[Đà Lạt]] sau.");

    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("Đà Lạt")).toHaveClass("missing");
    expect(screen.getByText(`(${vi.wiki.missingLink})`)).toHaveClass("sr-only");
  });

  it("still sends an ordinary link out of the app rather than into the vault", () => {
    mount("Xem [trang chủ](https://example.com).");

    const link = screen.getByRole("link", { name: "trang chủ" });
    expect(link).toHaveAttribute("href", "https://example.com");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("draws the machine's related block as chips, without its comment markers", async () => {
    const { onOpen, view } = mount(
      "Chữ của tác giả.\n\n<!-- wiki:related -->\n\n## Liên quan\n\n" +
        "Được nhắc tới ở: [[tra-sang]]\n\n<!-- /wiki:related -->\n",
    );

    expect(view.container).not.toHaveTextContent("wiki:related");
    const related = screen.getByRole("navigation", { name: vi.wiki.related });
    await userEvent.click(within(related).getByRole("button", { name: "Trà sáng" }));
    expect(onOpen).toHaveBeenCalledWith("tra-sang");
  });

  it("says a page has no words yet rather than showing nothing", () => {
    mount("<!-- wiki:related -->\n<!-- /wiki:related -->");
    expect(screen.getByText(vi.wiki.bodyEmpty)).toBeInTheDocument();
  });
});
