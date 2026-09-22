import { expect, test } from "@playwright/test";
import { type Conversation, coachAgent, defaultAgent, mockApi, run } from "./mock-api";

function conversation(id: string, title: string): Conversation {
  return {
    id,
    agent_id: "default",
    channel: "",
    title,
    created_at: "",
    updated_at: "",
    autonomous: false,
    cost_cap_usd: 1,
    skills: [],
    auto_approve: [],
    spent_usd: 0,
    unknown_cost_calls: 0,
    status: "idle",
    over_budget: false,
    messages: [],
    pending_approval: null,
  };
}

const mine = run({
  id: "mine",
  conversation_id: "c1",
  status: "running",
  finished_at: null,
  summary: "",
  title: "Việc của cuộc một",
});

const theirs = run({
  id: "theirs",
  conversation_id: "c2",
  status: "running",
  finished_at: null,
  summary: "",
  title: "Việc của cuộc hai",
});

// The delegate works on c1's behalf, so its run belongs to c1's strip too.
const delegated = run({
  id: "delegated",
  agent_id: "coach",
  conversation_id: "child-of-c1",
  source: "delegate:c1",
  status: "running",
  finished_at: null,
  summary: "",
  title: "Việc đã giao",
});

const options = {
  agents: [defaultAgent, coachAgent],
  conversations: [conversation("c1", "Cuộc một"), conversation("c2", "Cuộc hai")],
  stream: [{ type: "snapshot", runs: [mine, theirs, delegated] }],
};

test("the chat's strip shows this conversation's work and not another's", async ({ page }) => {
  await mockApi(page, options);
  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: /Cuộc một/ }).click();

  const strip = page.getByTestId("conversation-activity");
  await strip.getByRole("button", { name: "Xem chi tiết hoạt động" }).click();
  await expect(strip).toContainText("Việc của cuộc một");
  await expect(strip).not.toContainText("Việc của cuộc hai");

  // The strip stays open across the switch, so the second chat is compared in the same state.
  await page.getByRole("navigation").getByRole("button", { name: /Cuộc hai/ }).click();
  await expect(strip).toContainText("Việc của cuộc hai");
  await expect(strip).not.toContainText("Việc của cuộc một");
});

test("collapsed the strip is one progress line; opened it shows the delegated run under its parent", async ({ page }) => {
  await mockApi(page, options);
  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: /Cuộc một/ }).click();

  const strip = page.getByTestId("conversation-activity");
  await expect(strip.getByTestId("run-progress")).toHaveCount(1);
  await expect(strip.getByTestId("run-card")).toHaveCount(0);

  await strip.getByRole("button", { name: "Xem chi tiết hoạt động" }).click();

  await expect(strip.getByTestId("run-children")).toContainText("Việc đã giao");
  await expect(strip.getByTestId("run-children")).toContainText("HLV sức khoẻ");
});

test("a conversation that has never run shows no strip at all", async ({ page }) => {
  await mockApi(page, { ...options, stream: [{ type: "snapshot", runs: [theirs] }] });
  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: /Cuộc một/ }).click();

  await expect(page.getByTestId("conversation-activity")).toHaveCount(0);
});
