import { expect, test } from "@playwright/test";
import { mockApi } from "./mock-api";

test("send a message and read the streamed reply", async ({ page }) => {
  await mockApi(page, { turns: [[
    { type: "text_delta", text: "Xin chào" },
    { type: "assistant_message", message_id: "a1", content: "Xin chào từ agent", tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
    { type: "done", spent_usd: 0.05, unknown_cost_calls: 0 },
  ]] });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 2 })).toContainText("Xin chào");
  await page.getByRole("textbox").fill("hello");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("message-user")).toHaveText(/hello/);
  await expect(page.getByTestId("message-assistant")).toContainText("Xin chào từ agent");
  await expect(page.getByTestId("budget")).toContainText("$0.05 / $1.00");
});

test("a reply written in markdown arrives formatted, not as asterisks", async ({ page }) => {
  const reply = "**Giấc ngủ** quan trọng\n\n- ngủ sớm\n- dậy đúng giờ";
  await mockApi(page, { turns: [[
    { type: "assistant_message", message_id: "a1", content: reply, tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
    { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
  ]] });
  await page.goto("/");
  await page.getByRole("textbox").fill("ngủ thế nào");
  await page.keyboard.press("Enter");
  const bubble = page.getByTestId("message-assistant");
  await expect(bubble.locator("strong")).toHaveText("Giấc ngủ");
  await expect(bubble.locator("li")).toHaveText(["ngủ sớm", "dậy đúng giờ"]);
  await expect(bubble).not.toContainText("**");
});

test("approval bar pauses the turn and approving resumes it", async ({ page }) => {
  await mockApi(page, { turns: [
    [
      { type: "assistant_message", message_id: "a1", content: "", tool_calls: [{ id: "tc", name: "write_file", arguments: { path: "a.md" } }], provider: null, model: null, cost_usd: null },
      { type: "approval_required", approval_id: "ap", tool_call_id: "tc", name: "write_file", arguments: { path: "a.md" } },
    ],
    [
      { type: "tool_result", tool_call_id: "tc", name: "write_file", ok: true, output: "ok" },
      { type: "assistant_message", message_id: "a2", content: "Đã ghi.", tool_calls: [], provider: null, model: null, cost_usd: null },
      { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
    ],
  ] });
  await page.goto("/");
  await page.getByRole("textbox").fill("ghi tệp");
  await page.keyboard.press("Enter");
  const bar = page.getByRole("alertdialog");
  await expect(bar).toContainText("write_file");
  await expect(page.getByRole("textbox")).toBeDisabled();
  await bar.getByRole("button", { name: "Cho phép", exact: true }).click();
  await expect(page.getByTestId("message-assistant")).toContainText("Đã ghi.");
  await expect(page.getByTestId("tool-card")).toContainText("xong");
  await expect(page.getByRole("textbox")).toBeEnabled();
});

// A question pauses the turn the same way a tool approval does, but it closes by a
// different route. Before the question card, this row rendered as "Cho phép chạy
// ask_user?" with three buttons the server refuses, so a question asked in the browser
// was a dead end until it expired.
test("a question the agent asks is answered in the browser and resumes the turn", async ({ page }) => {
  const mock = await mockApi(page, { turns: [
    [
      { type: "assistant_message", message_id: "a1", content: "", tool_calls: [{ id: "tc", name: "ask_user", arguments: { question: "Dời hạn sang thứ sáu?" } }], provider: null, model: null, cost_usd: null },
      { type: "approval_required", approval_id: "aq", tool_call_id: "tc", name: "ask_user", arguments: { question: "Dời hạn sang thứ sáu?" }, kind: "question", options: ["có", "không"] },
    ],
    [
      { type: "tool_result", tool_call_id: "tc", name: "ask_user", ok: true, output: "{\"answered\": true}" },
      { type: "assistant_message", message_id: "a2", content: "Giữ nguyên hạn.", tool_calls: [], provider: null, model: null, cost_usd: null },
      { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
    ],
  ] });
  await page.goto("/");
  await page.getByRole("textbox").fill("xem hạn");
  await page.keyboard.press("Enter");

  const card = page.getByRole("alertdialog");
  await expect(card).toContainText("Dời hạn sang thứ sáu?");
  // The approve/deny wording belongs to a tool call; the server 409s it on this row.
  await expect(card.getByRole("button", { name: "Cho phép", exact: true })).toHaveCount(0);
  await expect(page.getByPlaceholder("Trả lời…")).toBeVisible();

  await card.getByRole("button", { name: "không", exact: true }).click();
  await expect(page.getByTestId("message-assistant")).toContainText("Giữ nguyên hạn.");
  const sent = mock.posted.find((r) => r.path.includes("/approvals/"));
  expect(sent?.path).toBe("/conversations/c1/approvals/aq/answer");
  expect(sent?.body).toEqual({ answer: "không" });
});

test("the settings section lists routes and key presence", async ({ page }) => {
  await mockApi(page);
  // Settings is a section of the crew's screen, reachable by link as well as by the
  // header's button, which needs a conversation open to be on screen.
  await page.goto("/#/manage/settings");
  const panel = page.getByTestId("manage-screen");
  await expect(panel).toContainText("fake:echo");
  await expect(panel).toContainText("chưa có");
  await expect(panel).toContainText("Asia/Ho_Chi_Minh");

  // Settings is a place rather than a layer over the chat, so leaving it is going back.
  await page.getByRole("button", { name: "← Chat" }).click();
  await expect(panel).toHaveCount(0);
});

/** A conversation paused on one write, as the server reports it after a reload. */
function pausedConversation() {
  const call = { id: "tc", name: "write_file", arguments: { path: "a.md" } };
  return {
    id: "c1", agent_id: "default", channel: "", title: "Ghi tệp", summary: "", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "awaiting_approval", over_budget: false, parent_call_id: "",
    messages: [{ id: "m1", seq: 1, role: "assistant", content: "", tool_calls: [call], tool_call_id: null, name: null, provider: null, model: null, cost_usd: null, created_at: "" }],
    pending_approval: { id: "ap", conversation_id: "c1", message_id: "m1", tool_call_id: "tc", tool_name: "write_file", arguments: call.arguments, status: "pending", created_at: "", expires_at: null, resolved_at: null, kind: "tool" },
  };
}

// Playwright answers a route with the whole body at once, so a stream that is still
// going when Stop is pressed has to be made in the page: the approved call starts, then
// the stream hangs the way a slow tool does, and says one more word later unless cut.
test("Stop on an approved call cuts its stream and leaves nothing spinning", async ({ page }) => {
  await page.addInitScript(() => {
    const realFetch = window.fetch.bind(window);
    const frame = (e: Record<string, unknown> & { type: string }) => new TextEncoder().encode(`event: ${e.type}\r\ndata: ${JSON.stringify(e)}\r\n\r\n`);
    window.fetch = async (input, init) => {
      if (!String(input).endsWith("/approvals/ap")) return realFetch(input, init);
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(frame({ type: "tool_call", tool_call_id: "tc", name: "write_file", arguments: { path: "a.md" } }));
          init?.signal?.addEventListener("abort", () => {
            (window as unknown as { streamCut: boolean }).streamCut = true;
            controller.error(new DOMException("aborted", "AbortError"));
          });
          setTimeout(() => {
            try {
              controller.enqueue(frame({ type: "text_delta", text: "chữ đến muộn" }));
            } catch {
              // Cut already: nothing more can be said.
            }
          }, 1500);
        },
      });
      return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
    };
  });
  await mockApi(page, { conversations: [pausedConversation()] });
  await page.goto("/#/chat/c1");

  await page.getByRole("alertdialog").getByRole("button", { name: "Cho phép", exact: true }).click();
  await expect(page.locator(".tool-status.running")).toHaveCount(1);
  await page.getByRole("button", { name: "Dừng" }).click();

  await expect(page.getByTestId("notice")).toContainText("Đã dừng lượt này.");
  await expect(page.locator(".tool-status.running")).toHaveCount(0);
  await expect(page.getByTestId("tool-card")).toContainText("đã dừng");
  expect(await page.evaluate(() => (window as unknown as { streamCut?: boolean }).streamCut)).toBe(true);
  // Past the moment the stream would have spoken again, had it not been cut.
  await page.waitForTimeout(1800);
  await expect(page.getByText("chữ đến muộn")).toHaveCount(0);
  await expect(page.getByRole("textbox")).toBeEnabled();
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("a spent cap is raised from the budget pill's card and the composer writes again", async ({ page }) => {
    await mockApi(page, { conversations: [{
      id: "c1", agent_id: "default", channel: "", title: "Chung", summary: "", created_at: "", updated_at: "",
      autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 1.2, unknown_cost_calls: 0,
      status: "idle", over_budget: true, parent_call_id: "", messages: [], pending_approval: null,
    }] });
    await page.goto("/#/chat/c1");
    await expect(page.getByTestId("over-budget")).toBeVisible();
    await expect(page.getByRole("textbox")).toBeDisabled();

    await page.getByTestId("budget").click();
    const card = page.getByRole("dialog", { name: "Chi phí cuộc trò chuyện" });
    await expect(card.getByTestId("cap-editor")).toContainText("$1.00");
    const step = card.getByRole("button", { name: "+$1.00" });
    expect((await step.boundingBox())!.height).toBeGreaterThanOrEqual(40);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await step.click();

    await expect(page.getByTestId("budget")).toContainText("$1.20 / $2.00");
    await expect(page.getByTestId("over-budget")).toBeHidden();
    await expect(page.getByRole("textbox")).toBeEnabled();
  });

  // The mocked stream ends after its snapshot and asks the browser to wait a minute, so
  // the pill soon shows the loss — as the phone sees it when the server restarts.
  test("a dropped live stream offers a thumb-sized retry that opens it again", async ({ page }) => {
    await mockApi(page);
    const opened: string[] = [];
    page.on("request", (request) => {
      if (new URL(request.url()).pathname === "/api/activity/stream") opened.push(request.url());
    });
    await page.goto("/");
    const retry = page.getByTestId("status-line").getByRole("button", { name: "Thử lại kết nối trực tiếp" });
    await expect(retry).toBeVisible();
    await expect(page.getByTestId("stream-state")).toContainText("Mất kết nối");
    expect((await retry.boundingBox())!.height).toBeGreaterThanOrEqual(40);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);

    const before = opened.length;
    await retry.click();
    await expect.poll(() => opened.length).toBeGreaterThan(before);
  });
});
