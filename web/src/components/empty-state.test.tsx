import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi as vitest } from "vitest";
import { EmptyState } from "./empty-state";

describe("EmptyState", () => {
  it("offers the way out next to the reason there is nothing here", async () => {
    const onClick = vitest.fn();
    render(<EmptyState says="Chưa có gì." action={{ label: "Bắt đầu", onClick }} />);

    expect(screen.getByText("Chưa có gì.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Bắt đầu" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  // Some sections are empty because nothing is happening, not because a step was
  // missed. Inventing a button there would send the person somewhere pointless.
  it("stays a plain sentence when there is nothing to do about it", () => {
    render(<EmptyState says="Chưa có gì." />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  // The icon is the section's own, so it says where the person is; the sentence still
  // carries the meaning, which is why the picture stays out of the accessibility tree.
  it("shows the section's icon only when given one, hidden from assistive technology", () => {
    const { container, rerender } = render(<EmptyState says="Chưa có gì." />);
    expect(container.querySelector(".empty-icon")).toBeNull();

    rerender(<EmptyState says="Chưa có gì." icon="clock" />);
    expect(container.querySelector(".empty-icon svg")).toHaveAttribute("aria-hidden", "true");
  });
});
