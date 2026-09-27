import { expect, type Page, test } from "@playwright/test";
import { coachAgent, defaultAgent, mockApi, run } from "./mock-api";

const master = { ...defaultAgent, name: "Trợ lý", delegates: ["coach"] };
const { kind: _kind, ...briefRow } = coachAgent.schedules[0];
const coach = { ...coachAgent, declared: { delegates: [], schedules: [briefRow] } };
const briefJob = {
  ...coachAgent.schedules[0],
  id: "coach/brief",
  schedule_id: "brief",
  agent_id: "coach",
  next_run: null,
  last_run: null,
  running: false,
  paused: false,
};

async function openJobs(page: Page, jobs: object[] = [briefJob]) {
  await mockApi(page, { agents: [master, coach], jobs });
  await page.goto("/#/manage/jobs");
}

for (const viewport of [
  { width: 390, height: 844 },
  { width: 1280, height: 800 },
]) {
  // The editor's bar is sticky, so a heading scrolled to the very top sits under it, and on
  // a phone the first row's name box went under it too.
  test(`Sửa lịch lands on the schedules below the editor's bar at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await openJobs(page);
    await page.getByTestId("job").getByRole("button", { name: "Sửa lịch Bản tin sáng" }).click();
    const editor = page.getByTestId("agent-editor");
    const heading = editor.getByRole("heading", { name: "Lịch chạy" });
    await expect(heading).toBeFocused();

    // Each box's top against the bar's bottom, read in one frame once the scroll settles.
    const clearance = () =>
      page.evaluate(() => {
        const bottom = document.querySelector(".editor-bar")!.getBoundingClientRect().bottom;
        const row = document.querySelector("[data-testid=schedule-row]")!;
        const name = [...row.querySelectorAll(".field-label")].find((el) => el.textContent === "Tên")!;
        const heading = document.querySelector("[data-testid=section-schedules] h3")!;
        const editor = document.querySelector("[data-testid=agent-editor]")!;
        return {
          heading: heading.getBoundingClientRect().top - bottom,
          name: name.getBoundingClientRect().top - bottom,
          // Above the bar: the page did scroll, or the two checks above prove nothing.
          scrolled: editor.getBoundingClientRect().top < document.querySelector(".editor-bar")!.getBoundingClientRect().top,
        };
      });
    await expect.poll(async () => (await clearance()).heading).toBeGreaterThanOrEqual(0);
    const settled = await clearance();
    expect(settled.name).toBeGreaterThanOrEqual(0);
    expect(settled.scrolled).toBe(true);
  });

  // A sticky box stops at its scroller's padding, so the bar stuck that far down and the form
  // scrolled past visibly in the strip above it.
  test(`the editor's bar sticks flush to the top of the page at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await openJobs(page);
    await page.getByTestId("job").getByRole("button", { name: "Sửa lịch Bản tin sáng" }).click();
    await expect(page.getByTestId("agent-editor").getByRole("heading", { name: "Lịch chạy" })).toBeFocused();

    const gap = () =>
      page.evaluate(() => {
        const bar = document.querySelector(".editor-bar")!;
        let scroller = bar.parentElement!;
        while (scroller.parentElement && !/auto|scroll/.test(getComputedStyle(scroller).overflowY))
          scroller = scroller.parentElement;
        return Math.round(bar.getBoundingClientRect().top - scroller.getBoundingClientRect().top - scroller.clientTop);
      });
    await expect.poll(gap).toBe(0);
  });
}

// Sửa lịch is how a job switched off in its profile is turned back on, so it must not look
// switched off itself: the row's text is dimmed, never the row's buttons.
test("a job off in its profile dims its text but not its buttons", async ({ page }) => {
  const off = { ...briefJob, id: "coach/off", schedule_id: "off", name: "Tắt sẵn", enabled: false };
  await openJobs(page, [briefJob, off]);
  const row = page.getByTestId("job").filter({ hasText: "Tắt sẵn" });
  await expect(row).toBeVisible();
  // The list fades in; measure once it has.
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished)));
  const shown = (selector: string) =>
    row.locator(selector).first().evaluate((el) => {
      let opacity = 1;
      for (let at: Element | null = el; at; at = at.parentElement) opacity *= Number(getComputedStyle(at).opacity);
      return { opacity, color: getComputedStyle(el).color };
    });

  for (const name of ["Sửa lịch Tắt sẵn", "Chạy ngay: Tắt sẵn"])
    expect((await shown(`button[aria-label="${name}"]`)).opacity, name).toBe(1);
  expect((await shown(".link-button")).opacity).toBe(1);
  // Still dimmed, as the rows beside it are not.
  const on = page.getByTestId("job").filter({ hasText: "Bản tin sáng" });
  const bright = await on.locator(".job-name").evaluate((el) => getComputedStyle(el).color);
  expect((await shown(".job-name")).color).not.toBe(bright);
});

// Checking several failing jobs is Sửa lịch or Xem riêng on one row, then back to the next:
// the back link returned to the crew or to all activity, and the row had to be found again.
test("the back link of a job's editor or run returns to that job's row", async ({ page }) => {
  const failed = run({ id: "r-err", agent_id: "coach", source: "job:coach/brief", status: "error" });
  const jobs = [{ ...briefJob, id: "coach/first", name: "Trước" }, { ...briefJob, last_run: failed }];
  await mockApi(page, { agents: [master, coach], jobs, runs: [failed] });
  await page.goto("/#/manage/jobs");
  const row = page.getByTestId("job").filter({ hasText: "Bản tin sáng" });

  await row.getByRole("button", { name: "Sửa lịch Bản tin sáng" }).click();
  await page.getByTestId("agent-editor").getByRole("button", { name: "← Lịch chạy" }).click();
  await expect(page).toHaveURL(/#\/manage\/jobs\/coach%2Fbrief$/);
  await expect(row).toBeFocused();

  await row.getByRole("button", { name: "Xem riêng lượt chạy gần nhất của Bản tin sáng" }).click();
  await expect(page.getByTestId("run-replay")).toBeVisible();
  // A reload keeps where the page was opened from.
  await page.reload();
  await page.getByTestId("run-replay").getByRole("button", { name: "← Lịch chạy" }).click();
  await expect(row).toBeFocused();

  // Opened from anywhere else, the back links still lead to their own lists.
  await page.goto("/#/manage/crew/coach");
  await page.getByTestId("agent-editor").getByRole("button", { name: "← Đội" }).click();
  await expect(page).toHaveURL(/#\/manage\/crew$/);
});
