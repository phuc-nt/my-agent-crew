import { expect, type Page, test } from "@playwright/test";
import { coachAgent, defaultAgent, mockApi } from "./mock-api";

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
