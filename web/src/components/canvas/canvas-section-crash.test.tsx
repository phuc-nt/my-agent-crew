import { fireEvent, render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import { NOTE, SHOP } from "../../test/canvas-dock-hook";
import { landed, startServer, stopServer } from "../../test/canvas-hook";
import { CanvasSection } from "./canvas-section";

// One canvas's page stands in for any that throws while it is drawn.
vitest.mock("./canvas-page", () => ({
  CanvasPage: ({ id }: { id: string }) => {
    if (id === "ba9876543210") throw new Error("vỡ");
    return <p data-testid="page">{id}</p>;
  },
}));

let opened: (string | null)[];

beforeEach(() => {
  startServer();
  vitest.spyOn(console, "error").mockImplementation(() => undefined);
  opened = [];
});

afterEach(stopServer);

const section = (over: Partial<ComponentProps<typeof CanvasSection>> = {}) => (
  <CanvasSection
    connected
    agentName={(id) => id}
    onOpenCanvas={(id) => opened.push(id)}
    conversations={[]}
    onOpenConversation={() => undefined}
    {...over}
  />
);

const back = () => screen.getByRole("button", { name: vi.canvas.back });

describe("a canvas page that breaks", () => {
  it("leaves the way back to the library standing above what broke", async () => {
    render(section({ canvasId: SHOP }));
    await landed();

    const crash = screen.getByRole("alert");
    expect(crash).toHaveTextContent(vi.crashed);
    expect(crash).not.toContainElement(back());
    expect(back().compareDocumentPosition(crash) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    fireEvent.click(back());
    expect(opened).toEqual([null]);
  });

  it("is left behind once the address names another canvas, or none", async () => {
    const view = render(section({ canvasId: SHOP }));
    await landed();
    expect(screen.getByRole("alert")).toHaveTextContent(vi.crashed);

    view.rerender(section({ canvasId: NOTE }));
    await landed();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByTestId("page")).toHaveTextContent(NOTE);

    view.rerender(section({ canvasId: SHOP }));
    view.rerender(section());
    await landed();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByTestId("canvas-library")).toBeInTheDocument();
  });
});
