import { expect, test, type Page, type Route } from "@playwright/test";

// Every /api call is answered in-browser so the smoke test measures the real DOM without a backend.
type Conversation = Record<string, unknown> & { id: string; messages: unknown[]; pending_approval: unknown };

const settings = {
  home: "/h",
  workspace_dir: "/h/workspace",
  routes: [{ provider: "fake", model: "echo" }],
  providers: ["fake"],
  language: "vi",
  cost_cap_usd: 1,
  max_steps: 20,
  autonomous_default: false,
  keys: { openrouter: false, brave: false, tavily: false },
  tools: [{ name: "write_file", description: "Ghi tệp", requires_approval: true }],
  skills: [{ name: "core", description: "", always: true }],
};

function sse(events: object[]): string {
  return events.map((e) => `event: ${(e as { type: string }).type}\r\ndata: ${JSON.stringify(e)}\r\n\r\n`).join("");
}

async function mockApi(page: Page, turns: object[][]) {
  const conversations: Conversation[] = [];
  let created = 0;
  await page.route(/^https?:\/\/[^/]+\/api\//, async (route: Route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    const method = route.request().method();
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/settings") return json(settings);
    if (path === "/conversations" && method === "GET") return json(conversations);
    if (path === "/conversations" && method === "POST") {
      const conv: Conversation = {
        id: `c${++created}`, title: "", created_at: "", updated_at: "", autonomous: false, cost_cap_usd: 1,
        skills: [], spent_usd: 0, unknown_cost_calls: 0, status: "idle", over_budget: false, messages: [], pending_approval: null,
      };
      conversations.push(conv);
      return json(conv, 201);
    }
    if (/\/(messages|approvals\/[^/]+)$/.test(path) && method === "POST") {
      const events = turns.shift() ?? [];
      return route.fulfill({ status: 200, contentType: "text/event-stream", body: sse(events) });
    }
    const conv = conversations.find((c) => path.startsWith(`/conversations/${c.id}`));
    if (conv && method === "GET") return json(conv);
    if (conv && method === "PATCH") return json(Object.assign(conv, route.request().postDataJSON()));
    return json({ detail: "no route" }, 404);
  });
}

test("send a message and read the streamed reply", async ({ page }) => {
  await mockApi(page, [[
    { type: "text_delta", text: "Xin chào" },
    { type: "assistant_message", message_id: "a1", content: "Xin chào từ agent", tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
    { type: "done", spent_usd: 0.05, unknown_cost_calls: 0 },
  ]]);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 2 })).toContainText("Xin chào");
  await page.getByRole("textbox").fill("hello");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("message-user")).toHaveText(/hello/);
  await expect(page.getByTestId("message-assistant")).toContainText("Xin chào từ agent");
  await expect(page.getByTestId("budget")).toContainText("$0.05 / $1.00");
});

test("approval bar pauses the turn and approving resumes it", async ({ page }) => {
  await mockApi(page, [
    [
      { type: "assistant_message", message_id: "a1", content: "", tool_calls: [{ id: "tc", name: "write_file", arguments: { path: "a.md" } }], provider: null, model: null, cost_usd: null },
      { type: "approval_required", approval_id: "ap", tool_call_id: "tc", name: "write_file", arguments: { path: "a.md" } },
    ],
    [
      { type: "tool_result", tool_call_id: "tc", name: "write_file", ok: true, output: "ok" },
      { type: "assistant_message", message_id: "a2", content: "Đã ghi.", tool_calls: [], provider: null, model: null, cost_usd: null },
      { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
    ],
  ]);
  await page.goto("/");
  await page.getByRole("textbox").fill("ghi tệp");
  await page.keyboard.press("Enter");
  const bar = page.getByRole("alertdialog");
  await expect(bar).toContainText("write_file");
  await expect(page.getByRole("textbox")).toBeDisabled();
  await bar.getByRole("button", { name: "Cho phép" }).click();
  await expect(page.getByTestId("message-assistant")).toContainText("Đã ghi.");
  await expect(page.getByTestId("tool-card")).toContainText("xong");
  await expect(page.getByRole("textbox")).toBeEnabled();
});

test("settings drawer lists routes and key presence", async ({ page }) => {
  await mockApi(page, []);
  await page.goto("/");
  await page.getByRole("button", { name: /Cài đặt/ }).click();
  const drawer = page.getByRole("dialog");
  await expect(drawer).toContainText("fake:echo");
  await expect(drawer).toContainText("chưa có");
  await drawer.getByRole("button", { name: "Đóng" }).click();
  await expect(drawer).toHaveCount(0);
});
