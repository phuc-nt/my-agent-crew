import { expect, test } from "@playwright/test";
import { coachAgent, defaultAgent, mockApi } from "./mock-api";

const master = { ...defaultAgent, name: "Trợ lý", delegates: ["coach"] };
// A kit defines it, so there is no manifest to patch and the editor may only show it.
const kitAgent = { ...coachAgent, id: "reviewer", name: "Người duyệt", editable: false, dir: "/h/.agents/agents/reviewer.md" };

test("an agent is opened from the crew, edited, and saved back", async ({ page }) => {
  await mockApi(page, { agents: [master, coachAgent] });
  await page.goto("/#/manage/crew");

  const crew = page.getByTestId("crew-list");
  await crew.getByTestId("crew-agent").nth(1).getByRole("button", { name: "Sửa" }).click();

  // The editor gets its own URL so it survives a reload and the Back button works.
  await expect(page).toHaveURL(/#\/manage\/crew\/coach$/);
  const editor = page.getByTestId("agent-editor");
  await expect(editor).toContainText("HLV sức khoẻ");
  await expect(editor.getByTestId("section-identity")).toBeVisible();
  await expect(editor.getByTestId("read-only")).toHaveCount(0);

  const name = editor.getByLabel("Tên", { exact: true });
  await name.fill("HLV mới");
  await editor.getByRole("button", { name: "Lưu", exact: true }).click();

  // A saved draft is no longer dirty, which is what puts the button back out of reach.
  await expect(editor.getByRole("button", { name: "Lưu", exact: true })).toBeDisabled();

  await editor.getByRole("button", { name: "← Đội" }).click();
  await expect(page).toHaveURL(/#\/manage\/crew$/);
  await expect(page.getByTestId("crew-list")).toContainText("HLV mới");
});

test("an agent a kit defines says so instead of offering a form that would be refused", async ({ page }) => {
  await mockApi(page, { agents: [master, kitAgent] });
  await page.goto("/#/manage/crew/reviewer");

  const editor = page.getByTestId("agent-editor");
  await expect(editor.getByTestId("read-only")).toContainText("không sửa được");
  await expect(editor.getByTestId("read-only")).toContainText("/h/.agents/agents/reviewer.md");
  await expect(editor.getByRole("button", { name: "Lưu", exact: true })).toBeDisabled();
  // Nothing a kit owns can be deleted from here either.
  await expect(editor.getByTestId("delete-agent")).toHaveCount(0);
});

test("a new agent is created from its id and opens in the editor", async ({ page }) => {
  await mockApi(page, { agents: [master] });
  await page.goto("/#/manage/crew");

  await page.getByRole("button", { name: "+ Thêm agent" }).click();
  const form = page.getByTestId("add-agent");
  await form.getByLabel("Mã agent").fill("scribe");
  await form.getByLabel("Tên hiển thị").fill("Thư ký");
  await form.getByRole("button", { name: "Tạo", exact: true }).click();

  await expect(page).toHaveURL(/#\/manage\/crew\/scribe$/);
  await expect(page.getByTestId("agent-editor")).toContainText("Thư ký");
});

test("the tools section says which agent has what, and connections names keys without values", async ({ page }) => {
  // The coach keeps an allow-list; the open agent names none, so the two ways a tool can
  // be absent are both on screen and have to read differently.
  const open = { ...coachAgent, id: "open", name: "Mở", tools: [] };
  await mockApi(page, { agents: [master, coachAgent, open] });
  await page.goto("/#/manage/tools");

  const matrix = page.getByTestId("tools-matrix");
  await expect(matrix.getByTestId("tool-row")).toHaveCount(2);
  const writeRow = matrix.getByTestId("tool-row").filter({ hasText: "write_file" });
  await expect(writeRow).toContainText("Ghi tệp");
  // Only the master is listed as having it; the coach's allow-list leaves it out.
  await expect(writeRow.locator("td.cell.on")).toHaveCount(1);
  const searchRow = matrix.getByTestId("tool-row").filter({ hasText: "web_search" });
  // An allow-list that omits it is a choice; no key at all is a missing prerequisite.
  await expect(searchRow.locator("td.cell.excluded")).toHaveCount(2);
  await expect(searchRow.locator("td.cell.missing-key")).toHaveCount(1);

  await page.getByRole("button", { name: "Kết nối" }).click();
  const panel = page.getByTestId("connections");
  await expect(panel.getByTestId("keys")).toContainText("OPENROUTER_API_KEY");
  await expect(panel.getByTestId("keys")).toContainText("BRAVE_API_KEY");
  await expect(panel.getByTestId("routes")).toContainText("echo");
  await expect(panel.getByTestId("telegram-list")).toContainText("TELEGRAM_BOT_TOKEN");
});

test("the editor shows what the agent is actually told, including a persona just written", async ({ page }) => {
  await mockApi(page, { agents: [master, coachAgent] });
  await page.goto("/#/manage/crew/coach");
  const editor = page.getByTestId("agent-editor");

  // A fresh agent has written no persona file, yet every one it could have is offered —
  // otherwise there is no way to write the first line from the web at all.
  const persona = editor.getByTestId("section-persona");
  await expect(persona.getByRole("tab", { name: /AGENTS\.md/ })).toBeVisible();
  await persona.getByRole("tab", { name: /AGENTS\.md/ }).click();
  await persona.getByRole("textbox").fill("Luôn trả lời ngắn.");
  await persona.getByRole("button", { name: "Ghi tệp" }).click();
  await expect(persona.getByRole("status")).toContainText("AGENTS.md");

  const prompt = editor.getByTestId("section-prompt");
  await prompt.getByRole("button", { name: "Xem lời nhắc" }).click();

  // The prompt is assembled server-side from the same code a turn uses, so the line that
  // was just saved is in it — which is how the person confirms the edit took effect.
  await expect(prompt.getByTestId("prompt-preview")).toContainText("Luôn trả lời ngắn.");
});
