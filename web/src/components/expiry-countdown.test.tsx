import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { vi } from "../i18n/vi";
import { ExpiryCountdown } from "./expiry-countdown";

const SECOND = 1000;

describe("ExpiryCountdown", () => {
  it.each([
    [9 * 60 * SECOND + 58 * SECOND, "9:58"],
    [500, "0:01"],
    [60 * 60 * SECOND, "1:00:00"],
    [61 * 60 * SECOND + 5 * SECOND, "1:01:05"],
    // An approval TTL set to a day, so a request waits overnight.
    [24 * 60 * 60 * SECOND, "24:00:00"],
  ])("reads %i ms left as %s", (remaining, clock) => {
    render(<ExpiryCountdown remaining={remaining} />);

    expect(screen.getByRole("timer")).toHaveTextContent(new RegExp(`^${vi.attentionExpiresIn(clock)}$`));
  });

  it("says the request expired once nothing is left", () => {
    render(<ExpiryCountdown remaining={0} />);

    expect(screen.getByRole("timer")).toHaveTextContent(vi.attentionExpired);
    expect(screen.getByRole("timer")).toHaveClass("expired");
  });
});
