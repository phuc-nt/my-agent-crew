import { expect, test } from "@playwright/test";
import { coachAgent, coderTemplate, defaultAgent, mockApi } from "./mock-api";

const master = { ...defaultAgent, name: "Trợ lý", delegates: ["coach"] };

test("one chat for the master: it names its team and there is no agent switcher", async ({ page }) => {
  await mockApi(page, { agents: [master, coachAgent] });
  await page.goto("/");

  await expect(page.getByRole("heading", { level: 2 })).toContainText("Tôi là Trợ lý");
  await expect(page.getByTestId("welcome-crew")).toContainText("HLV sức khoẻ");
  await expect(page.getByTestId("master-card")).toContainText("Trợ lý");
  await expect(page.getByRole("navigation").getByRole("radiogroup")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Đội/ })).toContainText("Đội: 1");
});

test("the crew tab lists the team and installs a bundled template in one click", async ({ page }) => {
  await mockApi(page, { agents: [master, coachAgent], templates: [coderTemplate] });
  await page.goto("/");
  await page.getByRole("button", { name: /Đội/ }).click();

  const crew = page.getByTestId("crew-list");
  await expect(crew.getByTestId("crew-agent")).toHaveCount(2);
  await expect(crew.getByTestId("crew-agent").first()).toContainText("điều phối");
  await expect(crew.getByTestId("crew-agent").nth(1)).toContainText("master giao được");

  const templates = page.getByTestId("template-list");
  await expect(templates).toContainText("Coder");
  await templates.getByRole("button", { name: "Cài" }).click();
  await expect(page.getByTestId("activity-panel").getByRole("status")).toContainText("Đã cài coder");
  await expect(crew.getByTestId("crew-agent")).toHaveCount(3);
  await expect(crew).toContainText("Coder");
  await expect(templates).toContainText("đã có");
  await expect(page.getByRole("button", { name: /Đội/ })).toContainText("Đội: 2");
});
