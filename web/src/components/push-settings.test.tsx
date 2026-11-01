import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi as vitest } from "vitest";
import type { Push } from "../hooks/use-push";
import { vi } from "../i18n/vi";
import type { PushState } from "../lib/push";
import { PushSettings } from "./push-settings";

function push(state: PushState | null, overrides: Partial<Push> = {}): Push {
  return { state, busy: false, note: null, enable: vitest.fn(), disable: vitest.fn(), test: vitest.fn(), ...overrides };
}

describe("notifications in the inbox", () => {
  it("offers the press while they are off", async () => {
    const off = push("off");
    render(<PushSettings push={off} />);
    expect(screen.getByText(vi.push.offHint)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: vi.push.enable }));
    expect(off.enable).toHaveBeenCalled();
  });

  it("offers a test and a way back once on, and says what the test did", async () => {
    const on = push("on", { note: vi.push.testSent });
    render(<PushSettings push={on} />);
    await userEvent.click(screen.getByRole("button", { name: vi.push.test }));
    await userEvent.click(screen.getByRole("button", { name: vi.push.disable }));
    expect(on.test).toHaveBeenCalled();
    expect(on.disable).toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent(vi.push.testSent);
  });

  it.each([
    ["install", vi.push.install],
    ["denied", vi.push.denied],
    ["unsupported", vi.push.unsupported],
  ] as const)("says why there is no press when %s", (state, says) => {
    render(<PushSettings push={push(state)} />);
    expect(screen.getByText(says)).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows nothing until the browser was asked", () => {
    const { container } = render(<PushSettings push={push(null)} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("holds the presses while one is under way", () => {
    render(<PushSettings push={push("off", { busy: true })} />);
    expect(screen.getByRole("button", { name: vi.push.enable })).toBeDisabled();
  });
});
