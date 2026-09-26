import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RunStep } from "../api/types";
import { fakeRun } from "../test/fake-backend";
import { RunCard } from "./run-timeline";

type ModelStep = Extract<RunStep, { kind: "model" }>;

function detailOf(step: Partial<ModelStep>): string | null {
  const answered: ModelStep = {
    kind: "model",
    chars: 42,
    provider: "openrouter",
    model: "deepseek",
    cost_usd: null,
    tool_calls: [],
    duration_ms: 3000,
    ...step,
  };
  render(<RunCard run={fakeRun({ steps: [answered] })} agentName="HLV" expanded />);
  const row = screen.getByTestId("run-step");
  return row.querySelector(".step-detail")?.textContent ?? null;
}

describe("a finished model step's detail line", () => {
  // The line the owner reads to tell a persona edit that kept the prompt cache from one
  // that broke it: a cache share that falls to nothing shows up here first.
  it("reads the route, the wait for the first word, the tokens with their cached part, and thinking", () => {
    const detail = detailOf({
      first_token_ms: 1_200,
      prompt_tokens: 12_300,
      cached_tokens: 8_100,
      thinking: true,
      tool_calls: ["read_file"],
    });

    expect(detail).toBe(
      "openrouter:deepseek · TTFT 1.2s · 12.3k tok (8.1k cache) · suy nghĩ · 42 ký tự · không rõ giá · → read_file",
    );
  });

  it("leaves out what the call did not report instead of printing a blank or a zero", () => {
    const detail = detailOf({ first_token_ms: null, prompt_tokens: 0, cached_tokens: null, cost_usd: 0.0021 });

    expect(detail).toBe("openrouter:deepseek · 42 ký tự · $0.0021");
  });

  it("shows the tokens without a cache figure when the provider does not report one", () => {
    const detail = detailOf({ first_token_ms: 850, prompt_tokens: 950 });

    expect(detail).toBe("openrouter:deepseek · TTFT 850ms · 950 tok · 42 ký tự · không rõ giá");
  });
});
