import { expect, test } from "@playwright/test";
import type { WikiPage } from "../src/api/types";
import { coachAgent, defaultAgent, mockApi, run, sse } from "./mock-api";

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

  // From the section list: the notice of a dropped stream offers a retry of the connection too.
  await page.getByRole("navigation", { name: "Mục quản lý" }).getByRole("button", { name: "Kết nối" }).click();
  const panel = page.getByTestId("connections");
  await expect(panel.getByTestId("credentials-model")).toContainText("OPENROUTER_API_KEY");
  await expect(panel.getByTestId("credentials-search")).toContainText("BRAVE_API_KEY");
  await expect(panel.getByTestId("routes").getByLabel("Mô hình")).toHaveValue("echo");
  await expect(panel.getByTestId("search-backends")).toContainText("firecrawl");
  await expect(panel.getByTestId("search-backends")).toContainText("duckduckgo");
  await expect(panel.getByTestId("telegram-list")).toContainText("TELEGRAM_BOT_TOKEN");
});

test("a key is set, checked and removed from Connections without its value ever showing", async ({ page }) => {
  await mockApi(page, { agents: [master] });
  await page.goto("/#/manage/connections");
  const brave = page.getByTestId("credential-BRAVE_API_KEY");
  await expect(brave).toContainText("chưa đặt");

  await brave.getByRole("button", { name: "Đặt" }).click();
  const field = brave.getByLabel("Giá trị cho BRAVE_API_KEY");
  await expect(field).toHaveAttribute("type", "password");
  await field.fill("brave-secret-123");
  await brave.getByRole("button", { name: "Lưu" }).click();
  await expect(brave).toContainText("đã đặt");
  await expect(brave.getByRole("status")).toBeVisible();
  await expect(page.getByTestId("connections")).not.toContainText("brave-secret-123");

  const router = page.getByTestId("credential-OPENROUTER_API_KEY");
  await router.getByRole("button", { name: "Kiểm tra" }).click();
  await expect(router.getByRole("status")).toContainText("Khoá hợp lệ.");

  page.once("dialog", (dialog) => dialog.accept());
  await brave.getByRole("button", { name: "Xoá" }).click();
  await expect(brave).toContainText("chưa đặt");

  const add = page.getByTestId("credential-add");
  await add.getByLabel("Tên biến mới", { exact: true }).fill("goodreads_id");
  await add.getByLabel("Giá trị cho GOODREADS_ID").fill("42");
  await add.getByRole("button", { name: "Thêm" }).click();
  await expect(page.getByTestId("credentials-other")).toContainText("GOODREADS_ID");
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
  // This agent has saved no note, so there is nothing a first message would be read after.
  await expect(prompt.getByTestId("prompt-opening")).toHaveCount(0);
});

test("the notes an agent reads beside its first message are shown apart from its prompt", async ({ page }) => {
  const opening = "[Bộ nhớ của bạn]\n## memory/2026-10-06.md\n- 07:00 dậy sớm\n[Hết phần bộ nhớ]";
  await mockApi(page, { agents: [master, coachAgent], promptOpening: opening });
  await page.goto("/#/manage/crew/coach");
  const prompt = page.getByTestId("agent-editor").getByTestId("section-prompt");

  await prompt.getByRole("button", { name: "Xem lời nhắc" }).click();

  // A note saved today is no longer in the system prompt; looked for there it would seem
  // lost. It is under the prompt, named for what it is, with a length of its own.
  await expect(prompt.getByTestId("prompt-preview")).not.toContainText("dậy sớm");
  await expect(prompt.getByRole("heading", { name: "Đọc ngay trước tin đầu của cuộc mới" })).toBeVisible();
  await expect(prompt.getByTestId("prompt-opening")).toHaveText(opening);
  await expect(prompt.getByText(`${opening.length} ký tự`, { exact: true })).toBeVisible();
  // Both boxes scroll inside the section; neither may push the page sideways.
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);

  await prompt.getByRole("button", { name: "Ẩn" }).click();
  await expect(prompt.getByTestId("prompt-opening")).toHaveCount(0);
});

test("the routes every agent falls back on are edited and saved", async ({ page }) => {
  await mockApi(page, { agents: [master] });
  await page.goto("/#/manage/connections");
  const routes = page.getByTestId("routes");
  const save = routes.getByRole("button", { name: "Lưu tuyến" });
  await expect(routes.getByTestId("routes-source")).toContainText("config.yaml");
  await expect(save).toBeDisabled();

  await routes.getByRole("button", { name: "+ Thêm tuyến" }).click();
  await routes.getByLabel("Mô hình").nth(1).fill("second");
  await save.click();
  await expect(routes.getByRole("status")).toContainText("Đã lưu");
  await expect(routes.getByLabel("Mô hình")).toHaveCount(2);
  await expect(save).toBeDisabled();

  // Reloading shows what the server kept, not what the page last had in memory.
  await page.reload();
  await expect(page.getByTestId("routes").getByLabel("Mô hình").nth(1)).toHaveValue("second");
});

test("a schedule is added from the jobs list through the agent's editor", async ({ page }) => {
  const { kind: _kind, ...briefRow } = coachAgent.schedules[0];
  const coach = { ...coachAgent, declared: { delegates: [], schedules: [briefRow] } };
  const briefJob = { ...coachAgent.schedules[0], id: "coach/brief", schedule_id: "brief", agent_id: "coach", next_run: null, last_run: null, running: false, paused: false };
  // What the scheduler serves. It builds the list at boot, so it changes only on a restart.
  const jobs: object[] = [briefJob];
  await mockApi(page, { agents: [master, coach], jobs });
  await page.goto("/#/manage/jobs");

  await page.getByTestId("job").getByRole("button", { name: "Sửa lịch Bản tin sáng" }).click();
  // The job rides along so the editor's back link returns to its row.
  await expect(page).toHaveURL(/#\/manage\/crew\/coach\/schedules\?job=coach%2Fbrief$/);
  const editor = page.getByTestId("agent-editor");
  await expect(editor.getByRole("heading", { name: "Lịch chạy" })).toBeFocused();

  await editor.getByRole("button", { name: "+ Thêm lịch" }).click();
  const row = editor.getByTestId("schedule-row").nth(1);
  await row.getByLabel("Tên", { exact: true }).fill("Dọn rác");
  await row.getByRole("button", { name: "Chu kỳ" }).click();
  await row.getByLabel("Chu kỳ", { exact: true }).fill("30m");
  await row.getByRole("button", { name: "Lệnh shell" }).click();
  await row.getByLabel("Lệnh shell", { exact: true }).fill("echo dọn");

  const patch = page.waitForRequest((r) => r.method() === "PATCH" && /\/api\/agents\/coach$/.test(r.url()));
  await editor.getByRole("button", { name: "Lưu", exact: true }).click();
  const sent = (await patch).postDataJSON() as { profile: { schedules: Record<string, unknown>[] } };
  expect(sent.profile.schedules).toEqual([
    { id: "brief", name: "Bản tin sáng", cron: "0 7 * * *", prompt: "Tóm tắt", enabled: true, skills: ["goodreads"] },
    { name: "Dọn rác", every: "30m", command: "echo dọn", enabled: true, skills: [] },
  ]);
  await expect(editor.getByTestId("restart-banner")).toBeVisible();
  await expect(editor.getByRole("button", { name: "Lưu", exact: true })).toBeDisabled();

  // The restart the banner asks for: the scheduler comes back with the new row in its list.
  jobs.push({ ...briefJob, id: "coach/job-1", schedule_id: "job-1", name: "Dọn rác", kind: "command", cron: null, every: "30m", prompt: null, command: "echo dọn", skills: [] });
  await page.goto("/#/manage/jobs");
  await page.reload();
  await expect(page.getByTestId("job").filter({ hasText: "Dọn rác" })).toContainText("Mỗi 30 phút");
  await expect(page.getByTestId("job").filter({ hasText: "Dọn rác" })).toContainText("30m");
});

test("a job reads its schedule in words, shows its last run, and a failure is counted on the nav", async ({ page }) => {
  const failed = run({ id: "r-err", agent_id: "coach", source: "job:coach/brief", status: "error", summary: "Không gọi được API" });
  const brief = { ...coachAgent.schedules[0], id: "coach/brief", schedule_id: "brief", agent_id: "coach", next_run: null, last_run: failed, running: false, paused: false };
  const weekly = { ...brief, id: "coach/weekly", schedule_id: "weekly", name: "Tổng kết tuần", cron: "0 18 * * 5", last_run: null };
  await mockApi(page, { agents: [master, coachAgent], jobs: [brief, weekly], runs: [failed] });
  await page.goto("/#/manage/jobs");

  const [first, second] = [page.getByTestId("job").nth(0), page.getByTestId("job").nth(1)];
  await expect(first).toContainText("Mỗi ngày 07:00");
  await expect(first.locator("code").first()).toHaveText("0 7 * * *");
  await expect(second).toContainText("Thứ Sáu hằng tuần 18:00");
  await expect(first.getByTestId("job-last")).toContainText("Không gọi được API");
  await expect(second.getByTestId("job-last")).toContainText("chưa chạy");

  // The count is drawn as a bare number and read out as the sentence it stands for.
  const nav = page.getByRole("navigation");
  await expect(nav.getByRole("button", { name: "Lịch chạy 1 lịch lỗi ở lần chạy gần nhất", exact: true })).toBeVisible();
  await expect(nav.getByTestId("jobs-failing")).toHaveText("11 lịch lỗi ở lần chạy gần nhất");
  // On a phone the nav is a sideways row with the jobs entry past its edge; the hidden
  // sentence must stay inside that row rather than widen the page.
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(first).toContainText("Mỗi ngày 07:00");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);

  await first.getByRole("button", { name: "Xem riêng lượt chạy gần nhất của Bản tin sáng" }).click();
  await expect(page).toHaveURL(/#\/manage\/activity\/r-err\?job=coach%2Fbrief$/);
  await expect(page.getByTestId("run-replay")).toContainText("Không gọi được API");
});

function wikiPage(over: Partial<WikiPage>): WikiPage {
  return { slug: "han-eco", kind: "entities", title: "Hạn Eco", status: "review", updated: "2026-09-25", sources: ["notes/2026-09-25.md"], questions: [], body: "", ...over };
}

test("a wiki page reads as prose, its link leads to the next page, and one tap marks it fine", async ({ page }) => {
  const vault = [
    wikiPage({ body: "Nộp **thứ tư**. Pha [[Trà sáng]] trước, hỏi [[Đà Lạt]] sau.", questions: ["Dời được không?"] }),
    wikiPage({ slug: "tra-sang", kind: "concepts", title: "Trà sáng", body: "Pha lúc 6h." }),
  ];
  await mockApi(page, { agents: [master], wiki: { default: vault } });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/manage/memory");
  await page.getByRole("tab", { name: "Wiki" }).click();

  const section = page.getByTestId("wiki-section");
  await section.getByRole("button", { name: "Hạn Eco" }).click();
  const opened = section.getByTestId("wiki-page");
  await expect(opened.getByRole("heading", { name: "Hạn Eco" })).toBeVisible();
  // Rendered, not the markdown source in a textarea.
  await expect(opened.locator("strong")).toHaveText("thứ tư");
  await expect(opened.getByRole("textbox")).toHaveCount(0);
  await expect(opened.locator(".wiki-link.missing")).toContainText("Đà Lạt");

  const fits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
  expect(fits).toBe(true);

  await opened.getByRole("button", { name: "Trà sáng" }).click();
  await expect(opened.getByRole("heading", { name: "Trà sáng" })).toBeVisible();
  await expect(opened).toContainText("Pha lúc 6h.");

  const status = opened.getByTestId("wiki-status");
  await expect(status).toHaveText("cần xem lại");
  const put = page.waitForRequest((request) => request.method() === "PUT" && /\/memory\/wiki\/pages\/tra-sang$/.test(request.url()));
  await opened.getByRole("button", { name: "Đánh dấu ổn" }).click();
  expect((await put).postDataJSON()).toEqual({ status: "ok" });
  await expect(status).toHaveText("ổn");
  await expect(opened.getByRole("button", { name: "Đánh dấu ổn" })).toHaveCount(0);
  // The button pressed is gone; the badge that now says so holds focus instead of <body>.
  await expect(status).toBeFocused();
});

test("a compile that ends while the stream is down lets go of its chip on the reconnect", async ({ page }) => {
  await mockApi(page, { agents: [master], wiki: { default: [] } });
  const compile = run({ id: "wiki-1", source: "memory:wiki", status: "running", finished_at: null, summary: "" });
  let started = false;
  let seen = false;
  let ended = false;
  const answer = (route: import("@playwright/test").Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  // Registered after mockApi, so these routes answer first.
  await page.route(/\/api\/agents\/default\/memory\/wiki\/compile$/, (route) => {
    started = true;
    return answer(route, { agent_id: "default", run_source: "memory:wiki" }, 202);
  });
  // Every answer ends the stream and the browser is back 100 ms later, as on a phone that
  // keeps dropping it. The run is seen once, running, and no snapshot lists it after that.
  await page.route(/\/api\/activity\/stream$/, (route) => {
    const events: object[] = [{ type: "snapshot", runs: [] }];
    if (started && !seen) events.push({ type: "run", run: compile });
    seen ||= started;
    return route.fulfill({ status: 200, contentType: "text/event-stream", body: sse(events, 100) });
  });
  const done = { ...compile, status: "done", finished_at: "2026-09-19T08:00:05Z", summary: "Đề xuất 1 trang." };
  await page.route(/\/api\/activity\/runs(\?|$)/, (route) => answer(route, ended ? [done] : []));
  await page.goto("/#/manage/memory");
  await page.getByRole("tab", { name: "Wiki" }).click();

  const section = page.getByTestId("wiki-section");
  const button = section.getByRole("button", { name: "Dựng wiki" });
  await button.click();
  await expect(section.locator(".run-chip")).toContainText("đang chạy");
  await expect(button).toBeDisabled();

  // It ends between two connections: only the run list can say so now.
  ended = true;
  await expect(section.getByText("Đề xuất 1 trang.")).toBeVisible({ timeout: 5_000 });
  await expect(section.locator(".run-chip")).toHaveCount(0);
  await expect(button).toBeEnabled();
});
