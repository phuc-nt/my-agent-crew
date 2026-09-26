import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import { UpdateBar } from "./update-bar";

it("reloads the page from its button", async () => {
  const reload = vitest.fn();
  render(<UpdateBar onReload={reload} />);
  expect(screen.getByRole("status")).toHaveTextContent(`${vi.updateAvailable}${vi.reload}`);
  await userEvent.click(screen.getByRole("button", { name: vi.updateReloadLabel }));
  expect(reload).toHaveBeenCalledOnce();
});
