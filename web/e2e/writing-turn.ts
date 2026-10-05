import { expect, type Page } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeCanvas } from "../src/test/fake-canvas";
import { holdTurn } from "./live-stream";
import { type Conversation, mockApi } from "./mock-api";

/** A turn in which the agent writes a canvas, held open so a spec feeds it the call piece by piece. */

export const ASKED = "viết kế hoạch tuần";

/** A piece of the arguments of the call that makes a canvas, as the model writes them. */
export const piece = (chunk: string) => ({ type: "tool_call_delta", index: 0, name: "artifact_create", chunk, attempt: 0 });

/** A conversation with nothing said in it yet. */
function quiet(): Conversation {
  return {
    id: "c1", agent_id: "default", channel: "", title: "Kế hoạch", summary: "", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "idle", over_budget: false, parent_call_id: "", pending_approval: null, messages: [],
  };
}

/** The first message is sent, and the turn it starts stays open for the test to feed. */
export async function ask(page: Page) {
  const canvas = new FakeCanvas();
  const turn = await holdTurn(page, "c1");
  await mockApi(page, { conversations: [quiet()], canvas });
  await page.goto("/#/chat/c1");
  const box = page.getByRole("textbox", { name: vi.composerPlaceholder });
  await box.fill(ASKED);
  await box.press("Enter");
  await expect(page.getByTestId("message-user")).toContainText(ASKED);
  return { box, canvas, turn };
}

export const frame = (page: Page) => page.getByTestId("canvas-writing");
export const card = (page: Page) => page.getByTestId("canvas-writing-card");
