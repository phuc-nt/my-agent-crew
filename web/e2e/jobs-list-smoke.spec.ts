import { expect, type Page, test } from "@playwright/test";
import { coachAgent, defaultAgent, mockApi, run } from "./mock-api";

const master = { ...defaultAgent, name: "Trợ lý", delegates: ["coach"] };
const { kind: _kind, ...briefRow } = coachAgent.schedules[0];
const coach = { ...coachAgent, declared: { delegates: [], schedules: [briefRow], tools: [] } };
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

// The nightly memory pass is a job too, and no row of the agent's schedules.
const memoryJob = { ...briefJob, id: "coach/memory-consolidate", schedule_id: "memory-consolidate", name: "Gom ghi nhớ", kind: "consolidate", prompt: null, skills: [] };

async function openJobs(page: Page, jobs: object[] = [briefJob]) {
  await mockApi(page, { agents: [master, coach], jobs });
  await page.goto("/#/manage/jobs");
}

/** The top of what the editor landed on and of the first row's name against the bottom of
 *  the editor's bar, read in one frame, and the gap a landing keeps below the bar, in pixels. */
const clearance = (page: Page, landing: string) =>
  page.evaluate((landing) => {
    const bottom = document.querySelector(".editor-bar")!.getBoundingClientRect().bottom;
    const row = document.querySelector("[data-testid=schedule-row]")!;
    const name = [...row.querySelectorAll(".field-label")].find((el) => el.textContent === "Tên")!;
    const editor = document.querySelector("[data-testid=agent-editor]")!;
    const probe = document.body.appendChild(document.createElement("div"));
    probe.style.height = "var(--space-2)";
    const gap = probe.getBoundingClientRect().height;
    probe.remove();
    return {
      landed: document.querySelector(landing)!.getBoundingClientRect().top - bottom,
      name: name.getBoundingClientRect().top - bottom,
      gap,
      // Above the bar: the page did scroll, or the checks below prove nothing.
      scrolled: editor.getBoundingClientRect().top < document.querySelector(".editor-bar")!.getBoundingClientRect().top,
    };
  }, landing);

for (const viewport of [
  { width: 390, height: 844 },
  { width: 1280, height: 800 },
]) {
  // The editor's bar is sticky, so what is scrolled to the very top sits under it: the row
  // of the job whose link was pressed, or the heading for a job that has no row, and on a
  // phone the row's name box went under it too.
  for (const [what, job, landing] of [
    ["the job's own row", "Bản tin sáng", "[data-testid=schedule-row]"],
    ["the schedules' heading for the memory pass, which has no row", "Gom ghi nhớ", "[data-testid=section-schedules] h3"],
  ]) {
    test(`Sửa lịch lands on ${what}, below the editor's bar at ${viewport.width}px`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await openJobs(page, [briefJob, memoryJob]);
      await page.getByTestId("job").getByRole("button", { name: `Sửa lịch ${job}` }).click();
      await expect(page.getByTestId("agent-editor").locator(landing)).toBeFocused();

      await expect.poll(async () => (await clearance(page, landing)).landed).toBeGreaterThanOrEqual(0);
      const settled = await clearance(page, landing);
      // Below the bar by that gap and no more: a margin that also counted the page's top
      // padding left the schedules a strip lower than the bar needs.
      expect(settled.landed).toBeLessThanOrEqual(settled.gap + 1);
      expect(settled.name).toBeGreaterThanOrEqual(0);
      expect(settled.scrolled).toBe(true);
    });
  }

  // A sticky box stops at its scroller's padding, so the bar stuck that far down and the form
  // scrolled past visibly in the strip above it.
  test(`the editor's bar sticks flush to the top of the page at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await openJobs(page);
    await page.getByTestId("job").getByRole("button", { name: "Sửa lịch Bản tin sáng" }).click();
    await expect(page.getByTestId("agent-editor").getByTestId("schedule-row").first()).toBeFocused();

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

// A failed badge reads the same after one bad run as after a week of them. The row says how
// long the job has been failing, whether the owner was told and when it is told again: one
// sentence, which takes a line of the row and wraps on a phone rather than widening it.
for (const width of [1440, 390]) {
  test(`a job that keeps failing says since when and what the owner was told, at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    const failed = run({ id: "r-err", agent_id: "coach", source: "job:coach/brief", status: "error" });
    // Days long past, so each time reads as a date and a clock in the page's zone (UTC+7).
    const failing = { count: 3, since: "2025-03-03T00:00:00Z", told_at: "2025-03-03T00:01:00Z", next_notice_at: "2025-03-04T00:01:00Z" };
    await openJobs(page, [{ ...briefJob, last_run: failed, failing }, { ...briefJob, id: "coach/fine", name: "Ổn" }]);

    const row = page.getByTestId("job").filter({ hasText: "Bản tin sáng" });
    const streak = row.getByTestId("job-failing");
    await expect(streak).toHaveText(
      "Hỏng 3 lần liên tiếp từ 03/03 07:00. Đã báo Telegram lúc 03/03 07:01; còn hỏng thì nhắc lại sau 04/03 07:01.",
    );
    // A row whose job is in no streak says nothing.
    await expect(page.getByTestId("job").filter({ hasText: "Ổn" })).toBeVisible();
    await expect(page.getByTestId("job").filter({ hasText: "Ổn" }).getByTestId("job-failing")).toHaveCount(0);

    const box = await page.evaluate(() => {
      const line = document.querySelector("[data-testid=job-failing]")!;
      const last = line.closest("[data-testid=job-last]")!.getBoundingClientRect();
      const { left, right, top, height } = line.getBoundingClientRect();
      const badge = line.parentElement!.querySelector(".badge")!.getBoundingClientRect();
      return {
        fits: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        within: left >= last.left - 1 && right <= last.right + 1,
        below: top >= badge.bottom,
        wrapped: height > 2 * parseFloat(getComputedStyle(line).fontSize),
      };
    });
    expect(box.fits).toBe(true);
    expect(box.within).toBe(true);
    // Under the badge and the time, not squeezed in beside them.
    expect(box.below).toBe(true);
    if (width === 390) expect(box.wrapped).toBe(true);
  });
}

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
