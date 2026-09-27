import { expect, test } from "@playwright/test";
import { type Conversation, coachAgent, defaultAgent, mockApi, run } from "./mock-api";

// A phone, not a narrow desktop window: the width people actually hold.
test.use({ viewport: { width: 390, height: 844 } });

function conversation(id: string, title: string): Conversation {
  return {
    id,
    agent_id: "default",
    channel: "",
    title,
    summary: "",
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
    parent_call_id: "",
    messages: [],
    pending_approval: null,
  };
}

const older = run({ id: "older", agent_id: "coach", title: "Dọn kho", summary: "Đã xong hôm qua" });

/**
 * Nothing may be wider than the screen.
 *
 * A single over-wide element gives the whole page a horizontal scrollbar, and
 * then every tap-target drifts as the person scrolls sideways looking for it.
 * Asserting on the document's own scroll width catches that wherever it comes
 * from, which a per-element width assertion would not.
 */
async function widestOverflow(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    const offenders: string[] = [];
    for (const el of document.querySelectorAll("*")) {
      const box = el.getBoundingClientRect();
      if (box.width > window.innerWidth + 1 && box.height > 0) {
        offenders.push(`${el.tagName.toLowerCase()}.${String(el.className).split(" ")[0]}`);
      }
    }
    return { scrollWidth: document.documentElement.scrollWidth, width: window.innerWidth, offenders };
  });
}

test("the conversation takes the whole screen and the list slides in over it", async ({ page }) => {
  await mockApi(page, {
    agents: [defaultAgent, coachAgent],
    runs: [],
    conversations: [conversation("c1", "Chung"), conversation("c2", "Ôn thi")],
  });
  await page.goto("/");

  // The thread and the composer own the screen; the list waits behind the menu button,
  // the way every messaging app on the phone already works.
  const sidebar = page.locator(".sidebar");
  await expect(page.getByRole("textbox", { name: /^Nhắn cho agent/ })).toBeVisible();
  await expect(sidebar).toBeHidden();

  const overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);

  // Opened, the list is wholly on screen, and picking a conversation puts it away again.
  const menu = page.getByRole("button", { name: "Mở danh sách cuộc trò chuyện" });
  await menu.click();
  await expect(sidebar).toBeVisible();
  await expect.poll(async () => (await sidebar.boundingBox())?.x).toBe(0);
  await sidebar.getByRole("button", { name: /Ôn thi/ }).click();
  await expect(sidebar).toBeHidden();
  await expect(page.locator(".conversation-header")).toContainText("Ôn thi");

  // Escape closes it as well, and the keyboard lands back on the button that opened it
  // rather than on a control inside a panel nobody can see.
  await menu.click();
  await expect(sidebar).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(sidebar).toBeHidden();
  await expect(menu).toBeFocused();
});

// On a phone every switch goes through the drawer, so a message started in one
// conversation must still be there after a look at another.
test("a half-written message waits in its conversation across drawer switches", async ({ page }) => {
  await mockApi(page, {
    agents: [defaultAgent, coachAgent],
    runs: [],
    conversations: [conversation("c1", "Chung"), conversation("c2", "Ôn thi")],
  });
  await page.goto("/");
  const box = page.getByRole("textbox", { name: /^Nhắn cho agent/ });
  const sidebar = page.locator(".sidebar");
  const menu = page.getByRole("button", { name: "Mở danh sách cuộc trò chuyện" });
  const open = async (title: string) => {
    await menu.click();
    await sidebar.getByRole("button", { name: new RegExp(title) }).click();
    await expect(page.locator(".conversation-header")).toContainText(title);
  };

  await open("Chung");
  await box.fill("Mai tập gì nhỉ");
  await open("Ôn thi");
  await expect(box).toHaveValue("");
  await open("Chung");
  await expect(box).toHaveValue("Mai tập gì nhỉ");
});

// A phone keyboard has no arrows worth using, so the command list is reached and used by
// thumb: a '/' button beside send and options big enough to tap.
test("the '/' button offers the agent's commands to a thumb, and the list fits", async ({ page }) => {
  const commands = [
    { name: "tong-ket", description: "Tổng kết ngày hôm nay thành một bản tin ngắn gửi qua Telegram", path: "/h/c/tong-ket.md" },
    { name: "plan", description: "Lập kế hoạch", path: "/h/c/plan.md" },
  ];
  await mockApi(page, { agents: [{ ...defaultAgent, commands }], conversations: [conversation("c1", "Chung")] });
  await page.goto("/");
  const box = page.getByRole("textbox", { name: /^Nhắn cho agent/ });
  const slash = page.getByRole("button", { name: "Chọn lệnh" });
  const size = await slash.boundingBox();
  expect(size?.width).toBeGreaterThanOrEqual(40);
  expect(size?.height).toBeGreaterThanOrEqual(40);

  await slash.click();
  const option = page.getByRole("option", { name: /tong-ket/ });
  await expect(option).toBeVisible();
  expect((await option.boundingBox())?.height).toBeGreaterThanOrEqual(40);
  const overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);

  await option.click();
  await expect(box).toHaveValue("/tong-ket ");
  await expect(page.getByRole("listbox")).toHaveCount(0);
});

/** Sends a message and waits for the agent's reply to be on screen. */
async function replied(page: import("@playwright/test").Page, content: string) {
  await mockApi(page, { turns: [[
    { type: "assistant_message", message_id: "a1", content, tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
    { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
  ]] });
  await page.goto("/");
  await page.getByRole("textbox", { name: /^Nhắn cho agent/ }).fill("chạy gì");
  await page.keyboard.press("Enter");
  const bubble = page.getByTestId("message-assistant");
  await expect(bubble).toBeVisible();
  return bubble;
}

// Over plain http a phone has no clipboard API, so the box to copy by hand is what the
// owner actually gets there, and he has to be able to put it away with a thumb.
test("a copy the phone cannot make opens a box a thumb can close", async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(navigator, "clipboard", { configurable: true, value: undefined }));
  const bubble = await replied(page, "Chạy:\n\n```\nls\n```");
  const copy = bubble.getByRole("button", { name: "Sao chép mã" });
  await copy.click();

  const close = page.getByTestId("copy-fallback").getByRole("button", { name: "Đóng" });
  const size = await close.boundingBox();
  expect(size?.width).toBeGreaterThanOrEqual(40);
  expect(size?.height).toBeGreaterThanOrEqual(40);
  await close.click();
  await expect(page.getByTestId("copy-fallback")).toHaveCount(0);
  await expect(copy).toBeFocused();
});

// The copy button is always shown on a phone and sized for a thumb, so it must fit inside
// even a one-line block, and a long command must not scroll underneath it.
test("a code block's copy button stays in its corner, clear of the code", async ({ page }) => {
  const long = "uv run python -m my_agent_crew --home /tmp/agent-home --port 9000 --log-level debug";
  const bubble = await replied(page, `Xem:\n\n\`\`\`\nls\n\`\`\`\n\nRồi:\n\n\`\`\`sh\n${long}\n\`\`\``);
  await expect(bubble.locator(".md-code")).toHaveCount(2);

  const blocks = await bubble.locator(".md-code").evaluateAll((all) =>
    all.map((block) => {
      const pre = block.querySelector("pre")!.getBoundingClientRect();
      const button = block.querySelector("button")!.getBoundingClientRect();
      // Whichever element scrolls sideways shows its text up to its client area's edge.
      const scroller = [block.querySelector("pre")!, block.querySelector("code")!].find(
        (el) => el.scrollWidth > el.clientWidth,
      );
      const shown = scroller && scroller.getBoundingClientRect().left + scroller.clientLeft + scroller.clientWidth;
      return { pre, button, scrolls: Boolean(scroller), shownRight: shown ?? 0 };
    }),
  );
  for (const { pre, button } of blocks) {
    expect(button.height).toBeGreaterThanOrEqual(40);
    expect(button.top).toBeGreaterThanOrEqual(pre.top);
    expect(button.bottom).toBeLessThanOrEqual(pre.bottom);
    expect(button.right).toBeLessThanOrEqual(pre.right);
  }
  expect(blocks[1].scrolls).toBe(true);
  expect(blocks[1].shownRight).toBeLessThanOrEqual(blocks[1].button.left);
  const overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);
});

test("the export in a conversation's options is big enough for a thumb", async ({ page }) => {
  await mockApi(page, { agents: [defaultAgent], runs: [], conversations: [conversation("c1", "Chung")] });
  await page.goto("/");
  await page.getByRole("button", { name: "Mở danh sách cuộc trò chuyện" }).click();
  await page.locator(".sidebar").getByRole("button", { name: /Chung/ }).click();
  await page.locator(".conversation-header").getByRole("button", { name: /Tuỳ chọn/ }).click();

  const exported = page.getByRole("button", { name: "Xuất Markdown" });
  await expect(exported).toBeVisible();
  expect((await exported.boundingBox())?.height).toBeGreaterThanOrEqual(40);
  const overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);
});

// The search box lives in the drawer, and a closed drawer is inert: a browser refuses to
// focus anything inside it, so the shortcut has to open the drawer around the box first.
test("the search shortcut opens the list at the search box", async ({ page }) => {
  const many = Array.from({ length: 9 }, (_, i) => conversation(`c${i}`, `Cuộc ${i}`));
  await mockApi(page, { agents: [defaultAgent, coachAgent], runs: [], conversations: many });
  await page.goto("/");
  await expect(page.getByRole("textbox", { name: /^Nhắn cho agent/ })).toBeVisible();

  await page.keyboard.press("ControlOrMeta+k");

  await expect(page.locator(".sidebar")).toBeVisible();
  await expect(page.getByRole("searchbox")).toBeFocused();
  // While the list covers the chat, the chat takes no focus: Tab stays in the list.
  await expect(page.locator("main")).toHaveAttribute("inert", "");
});

test("the manage sections stay reachable when the nav has no room to stack", async ({ page }) => {
  await mockApi(page, { agents: [defaultAgent, coachAgent], runs: [older] });
  await page.goto("/#/manage/activity");

  // The nav turns into one scrolling row; every section must still be clickable.
  await expect(page.getByTestId("manage-screen")).toBeVisible();
  await page.getByRole("button", { name: /Đội/ }).click();
  await expect(page).toHaveURL(/#\/manage\/crew/);

  const overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);
});

test("a run opened on its own still fits, timeline and all", async ({ page }) => {
  await mockApi(page, { agents: [defaultAgent, coachAgent], runs: [older] });
  await page.goto("/#/manage/activity/older");

  await expect(page.getByTestId("run-replay")).toBeVisible();
  const overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);
});

test("connections fit, keys, host defaults and an open key field included", async ({ page }) => {
  await mockApi(page, { agents: [defaultAgent, coachAgent] });
  await page.goto("/#/manage/connections");

  // Opened, a row is at its widest: the field and its two buttons share one line.
  const router = page.getByTestId("credential-OPENROUTER_API_KEY");
  await router.getByRole("button", { name: "Thay" }).click();
  await expect(router.getByLabel("Giá trị cho OPENROUTER_API_KEY")).toBeVisible();
  await expect(page.getByTestId("credential-OLLAMA_BASE_URL")).toContainText("11434");

  const overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);
});

test("the activity log's chips fold on a phone, then wrap and stay big enough to tap", async ({ page }) => {
  const runs = [
    older,
    run({ id: "web", source: "chat", status: "error", title: "Trả lời" }),
    run({ id: "tg", source: "telegram", status: "halted", title: "Nhắn Telegram" }),
    run({ id: "wiki", agent_id: "coach", source: "memory:wiki", title: "Sổ tay" }),
    run({ id: "sub", source: "delegate:c9", title: "Việc được giao" }),
    run({ id: "api", source: "api", title: "Gọi API" }),
  ];
  await mockApi(page, { agents: [defaultAgent, coachAgent], runs });
  await page.goto("/#/manage/activity");

  // Stacked, the three groups pushed every run below the fold of the page opened to see
  // them. Folded, the newest run is on screen at once, behind a toggle as big as a chip.
  const filters = page.getByTestId("run-filters");
  await expect(page.getByTestId("run-log").getByTestId("run-card").first()).toBeInViewport({ ratio: 1 });
  const fold = filters.getByRole("button", { name: /^Lọc/ });
  expect((await fold.boundingBox())?.height).toBeGreaterThanOrEqual(40);
  await expect(filters.getByRole("group", { name: "Trạng thái" })).toBeHidden();
  await fold.click();

  // Every group is on screen at once; a row that scrolled sideways would hide choices.
  await expect(filters.getByRole("button", { name: "Giao việc" })).toBeVisible();
  for (const chip of await filters.getByRole("button").all()) {
    const box = await chip.boundingBox();
    expect(box?.height).toBeGreaterThanOrEqual(40);
    expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(390);
  }

  // Narrowed to nothing, the way out is the one button in the empty box.
  await filters.getByRole("group", { name: "Agent" }).getByRole("button", { name: coachAgent.name }).click();
  await filters.getByRole("group", { name: "Trạng thái" }).getByRole("button", { name: /^đã dừng$/i }).click();
  const clear = page.getByTestId("run-log").getByRole("button", { name: "Bỏ lọc" });
  expect((await clear.boundingBox())?.height).toBeGreaterThanOrEqual(40);

  const overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);
});

// The widest the costs page gets: every figure in the millions, a long model id, the
// cache columns and the tiles two to a row. None of it may push the page sideways.
test("the costs page fits, cache columns and today's tiles included", async ({ page }) => {
  const usage = {
    calls: 1_234,
    cost_usd: 12.3456,
    prompt_tokens: 123_456_789,
    completion_tokens: 9_876_543,
    cached_tokens: 98_765_432,
    unknown_cost_calls: 3,
  };
  const days = Array.from({ length: 7 }, (_, i) => ({ day: `2026-09-${20 + i}`, ...usage }));
  const models = [
    { model: "openrouter:deepseek/deepseek-v4-flash-preview-2026-09", ...usage },
    { model: "ollama:qwen3", ...usage, cached_tokens: 0 },
  ];
  const call = {
    kind: "model",
    chars: 120,
    provider: "openrouter",
    model: "deepseek-v4-flash",
    cost_usd: 0.0012,
    tool_calls: ["read_file", "shell_run"],
    first_token_ms: 1_234,
    prompt_tokens: 45_678,
    cached_tokens: 40_000,
    thinking: true,
    duration_ms: 3_000,
  };
  const runs = [run({ id: "a", agent_id: "coach", steps: [call] }), run({ id: "b", steps: [call, call] })];
  const stats = {
    runs: 500,
    model_calls: 12_345,
    spent_usd: 123.45,
    unknown_cost_calls: 3,
    by_agent: { coach: 100, default: 23.45 },
    by_model: {},
    by_day: {},
    // What the runs above add up to, one call for the coach and two for the other.
    cache_by_agent: {
      coach: { prompt_tokens: 45_678, cached_tokens: 40_000 },
      default: { prompt_tokens: 91_356, cached_tokens: 80_000 },
    },
    days,
    models,
    pending_proposals: 0,
  };
  await mockApi(page, { agents: [defaultAgent, coachAgent], runs, stats });
  await page.goto("/#/manage/costs");

  await expect(page.getByTestId("stat-periods")).toContainText("Hôm nay");
  await expect(page.getByTestId("stat-periods")).toContainText("7 ngày");
  await expect(page.getByTestId("stat-models")).toContainText("98.8M · 80%");
  await expect(page.getByTestId("stat-agent-cache")).toContainText("40k · 88%");
  await expect(page.getByTestId("stats")).toContainText("500 lượt gần nhất");
  let overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);

  // The step's usage line is the longest line a run card carries.
  await page.goto("/#/manage/activity/a");
  await expect(page.getByTestId("run-replay")).toContainText("TTFT 1.2s · 45.7k tok (40k cache) · suy nghĩ");
  overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);
});

// Hidden or saying "no runs", a chat whose stored runs could not be read would pass for
// one that never ran.
test("a chat whose run history cannot be read says so, with a retry big enough to tap", async ({ page }) => {
  await mockApi(page, { agents: [defaultAgent, coachAgent], runs: [], conversations: [conversation("c1", "Chung")] });
  await page.route(/\/api\/activity\/runs\?.*conversation_id=/, (route) => route.abort());
  await page.goto("/#/chat/c1");

  const strip = page.getByTestId("conversation-activity");
  await expect(strip).toContainText("Không tải được lịch sử chạy.");
  const box = await strip.getByRole("button", { name: "Thử lại" }).boundingBox();
  expect(box?.height).toBeGreaterThanOrEqual(40);

  const overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);
});

// Reading a whole file before letting it be written must not cost the buttons that decide
// it: the height a phone browser leaves under its own bars, a 120-line file opened in full,
// and the page still one screen, decisions in reach, without scrolling the header away.
test("a request's full arguments leave its buttons on screen in a short phone view", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 664 });
  const content = Array.from({ length: 120 }, (_, i) => `dòng ${i + 1} của ghi chú`).join("\n");
  await mockApi(page, {
    agents: [defaultAgent, coachAgent],
    runs: [],
    conversations: [
      {
        ...conversation("c1", "Ghi chú"),
        status: "awaiting_approval",
        pending_approval: {
          id: "ap", conversation_id: "c1", message_id: "m", tool_call_id: "tc", tool_name: "write_file",
          arguments: { path: "notes/tuan-nay.md", content }, status: "pending", created_at: "2026-09-26T01:00:00Z",
          expires_at: "2099-01-01T00:00:00Z", resolved_at: null, kind: "tool", options: [],
        },
      },
    ],
  });
  await page.goto("/#/chat/c1");
  const bar = page.getByRole("alertdialog");
  await bar.getByRole("button", { name: "Xem đầy đủ" }).click();
  await expect(bar.locator(".args-detail-code").first()).toContainText("dòng 120");

  // Cho phép, Luôn cho phép and Từ chối, wherever the row wraps them.
  const fit = await bar.locator(".approval-actions").evaluate((el) => ({
    top: el.getBoundingClientRect().top,
    bottom: el.getBoundingClientRect().bottom,
    height: window.innerHeight,
    page: document.documentElement.scrollHeight,
  }));
  expect(fit.top).toBeGreaterThanOrEqual(0);
  expect(fit.bottom).toBeLessThanOrEqual(fit.height);
  expect(fit.page).toBeLessThanOrEqual(fit.height);
  await expect(page.locator(".conversation-header")).toBeInViewport();
});
