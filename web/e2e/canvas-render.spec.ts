import { expect, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeCanvas } from "../src/test/fake-canvas";
import { overflowing } from "./canvas-overflow";
import { type Conversation, mockApi } from "./mock-api";
import { smallTargets } from "./small-targets";

/**
 * A page an agent wrote, run by a real browser: in the frame the panel puts it in, and on its own
 * at the address the frame loads. What the page is kept from is the browser's doing, so only a
 * browser can show it; the page here comes with the policy and the reporter the server sends
 * (`mock-render.ts`).
 */

const PAGE = "0a0b0c0d0e0f";
const OTHER = "f0e0d0c0b0a0";
const TITLE = "Trang thử";
const { page: words, pageErrors } = vi.canvas;

const html = (body: string) =>
  `<!doctype html>\n<html lang="vi">\n<head><meta charset="utf-8"><title>${TITLE}</title></head>\n<body>\n${body}\n</body>\n</html>\n`;
const script = (code: string) => `<script>${code}</script>`;

/** What the server streams for a message: an answer, so the send ends as sent. */
const TURN = [
  { type: "assistant_message", message_id: "a1", content: "Để tôi xem.", tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
  { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
];

/** A conversation with nothing said in it yet, which the canvas is shared with. */
function quiet(): Conversation {
  return {
    id: "c1", agent_id: "default", channel: "", title: "Trang", summary: "", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "idle", over_budget: false, parent_call_id: "", pending_approval: null, messages: [],
  };
}

/** A server holding the agent's page whose body is `body`, and another page it could move to. */
async function serve(page: Page, body: string) {
  const fake = new FakeCanvas();
  fake.add({ id: PAGE, title: TITLE, kind: "html", agent_id: "master", content: html(body), conversationIds: ["c1"] });
  fake.add({ id: OTHER, title: "Trang khác", kind: "html", agent_id: "master", content: html("<p>Trang khác</p>") });
  await mockApi(page, { conversations: [quiet()], canvas: fake, turns: [TURN] });
}

/**
 * The page on show in the canvas beside or over the conversation, with the messages the browser
 * sends and every request the page itself makes after the one that loads it.
 */
async function openPage(page: Page, body: string) {
  await serve(page, body);
  const messages: unknown[] = [];
  const fromFrame: string[] = [];
  page.on("request", (request) => {
    const { pathname } = new URL(request.url());
    if (request.method() === "POST" && pathname === "/api/conversations/c1/messages") messages.push(request.postDataJSON());
    if (!request.isNavigationRequest() && request.frame() !== page.mainFrame()) fromFrame.push(`${request.method()} ${request.url()}`);
  });
  await page.goto("/#/chat/c1");
  await page.getByRole("button", { name: vi.canvas.buttonLabel(1) }).click();
  await page.getByRole("button", { name: new RegExp(TITLE) }).click();
  await expect(frame(page)).toBeVisible();
  return { messages, fromFrame };
}

const frame = (page: Page) => page.locator("iframe.canvas-frame");
const errors = (page: Page) => page.getByRole("group", { name: pageErrors.group });
const lines = (page: Page) => errors(page).locator(".canvas-error-message");

/** Waits for the page to have made `reported` reports, and `more` when the panel stopped hearing
 *  it there, opens the list and reads each as shown. */
async function listed(page: Page, reported: number, more = false): Promise<string[]> {
  await expect(errors(page).locator(".canvas-errors-count")).toHaveText(pageErrors.count(reported, more));
  await errors(page).getByRole("button", { name: pageErrors.show, exact: true }).click();
  await expect(lines(page).first()).toBeVisible();
  return lines(page).allTextContents();
}

/** Keeps, on the app's window, how long each report sent to it is as it arrives, before the app cuts it. */
async function recordPosted(page: Page) {
  await page.addInitScript(() => {
    if (window !== window.top) return;
    const posted: number[] = [];
    Object.assign(window, { posted });
    window.addEventListener("message", (event: MessageEvent<unknown>) => {
      const { data } = event;
      if (typeof data !== "object" || data === null) return;
      const { type, message } = data as { type?: unknown; message?: unknown };
      if (type === "canvas-error" && typeof message === "string") posted.push(message.length);
    });
  });
}

test.describe("a page opened by its address alone", () => {
  test("has an origin of its own and no storage, by the policy it comes with", async ({ page }) => {
    await serve(page, "<p>Một mình</p>");

    await page.goto(`/api/artifacts/${PAGE}/render`);

    await expect(page.getByText("Một mình")).toBeVisible();
    expect(await page.evaluate(() => window.origin)).toBe("null");
    const storage = await page.evaluate(() => {
      try {
        return typeof window.localStorage;
      } catch (error) {
        return (error as Error).name;
      }
    });
    expect(storage).toBe("SecurityError");
  });
});

test.describe("a page in the canvas beside a wide conversation", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("runs under an origin that is not the app's, and what it throws is listed", async ({ page }) => {
    await openPage(page, script('throw new Error("origin=" + window.origin);'));

    expect(await listed(page, 1)).toEqual(["Uncaught Error: origin=null"]);
  });

  test("cannot call the api: the policy stops the request before it leaves, and says so", async ({ page }) => {
    const { fromFrame } = await openPage(page, script('fetch("/api/conversations").catch(function () {});'));

    expect(await listed(page, 1)).toEqual([expect.stringMatching(/^connect-src blocked http:\/\/127\.0\.0\.1:\d+\/api\/conversations$/)]);
    expect(fromFrame).toEqual([]);
  });

  test("cannot keep anything in the browser's storage", async ({ page }) => {
    await openPage(page, script('localStorage.setItem("khoá", "giá trị");'));

    expect(await listed(page, 1)).toEqual([expect.stringMatching(/^Uncaught SecurityError: .*localStorage/)]);
  });

  test("cannot put a dialog over the app", async ({ page }) => {
    const dialogs: string[] = [];
    page.on("dialog", (dialog) => {
      dialogs.push(dialog.message());
      void dialog.dismiss();
    });

    await openPage(page, script('alert("x"); throw new Error("sau hộp thoại");'));

    expect(await listed(page, 1)).toEqual(["Uncaught Error: sau hộp thoại"]);
    expect(dialogs).toEqual([]);
  });

  test("cannot move the app to another address", async ({ page }) => {
    const moving = 'try { top.location = "about:blank"; throw new Error("moved"); } catch (error) { throw new Error("top.location: " + error.name); }';
    await openPage(page, script(moving));

    expect(await listed(page, 1)).toEqual(["Uncaught Error: top.location: SecurityError"]);
    expect(new URL(page.url()).hash).toBe("#/chat/c1");
    await expect(frame(page)).toBeVisible();
  });

  test("is taken out when it moves itself to another address, and the person is told", async ({ page }) => {
    const leaving = `window.addEventListener("load", function () { setTimeout(function () { location.href = "/api/artifacts/${OTHER}/render"; }, 0); });`;
    await serve(page, script(leaving));
    await page.goto("/#/chat/c1");
    await page.getByRole("button", { name: vi.canvas.buttonLabel(1) }).click();
    await page.getByRole("button", { name: new RegExp(TITLE) }).click();

    await expect(page.getByText(words.navigated)).toBeVisible();
    await expect(frame(page)).toHaveCount(0);
    await expect(page.getByRole("button", { name: words.reload, exact: true })).toBeVisible();
  });

  test("is the only window whose reports are listed: one the app posts to itself is not", async ({ page }) => {
    await openPage(page, `<button type="button" onclick="throw new Error('thật')">Hỏng</button>`);

    // Heard by every listener of the app's window before this one, the panel's among them.
    await page.evaluate(
      () =>
        new Promise<void>((resolve) => {
          window.addEventListener("message", () => resolve(), { once: true });
          window.postMessage({ type: "canvas-error", message: "giả", source: "", line: 1, column: 1 }, "*");
        }),
    );
    await page.frameLocator("iframe.canvas-frame").getByRole("button", { name: "Hỏng" }).click();

    expect(await listed(page, 1)).toEqual(["Uncaught Error: thật"]);
  });

  test("is heard for twenty of the twenty-five errors it throws, and the list keeps the newest five", async ({ page }) => {
    // The reporter stops at twenty. The page then posts a report of its own, which says the errors
    // before it have all arrived: twenty of them and this one.
    const burst = [
      "for (var n = 1; n <= 25; n++) setTimeout(function (at) { throw new Error('lỗi ' + at); }, 0, n);",
      'setTimeout(function () { parent.postMessage({ type: "canvas-error", message: "hết đợt", source: "", line: 0, column: 0 }, "*"); }, 0);',
    ].join("\n");
    await openPage(page, script(burst));

    expect(await listed(page, 21)).toEqual([
      "Uncaught Error: lỗi 17",
      "Uncaught Error: lỗi 18",
      "Uncaught Error: lỗi 19",
      "Uncaught Error: lỗi 20",
      "hết đợt",
    ]);
  });

  test("is heard out on fifty of the ten thousand reports it posts past the reporter", async ({ page }) => {
    const flood =
      'for (var n = 1; n <= 10000; n++) parent.postMessage({ type: "canvas-error", message: "tin " + n, source: "", line: 0, column: 0 }, "*");';
    await openPage(page, script(flood));

    expect(await listed(page, 50, true)).toEqual(["tin 46", "tin 47", "tin 48", "tin 49", "tin 50"]);
    // A message of the app's own later, the count has not moved: the page was not heard further.
    await page.evaluate(
      () =>
        new Promise<void>((resolve) => {
          window.addEventListener("message", () => resolve(), { once: true });
          window.postMessage("sau cùng", "*");
        }),
    );
    await expect(errors(page).locator(".canvas-errors-count")).toHaveText(pageErrors.count(50, true));
    expect(await lines(page).allTextContents()).toEqual(["tin 46", "tin 47", "tin 48", "tin 49", "tin 50"]);
  });

  test("reports a picture from elsewhere that the policy keeps it from loading", async ({ page }) => {
    const refused: string[] = [];
    page.on("requestfailed", (request) => refused.push(`${request.url()} ${request.failure()?.errorText}`));

    await openPage(page, '<img alt="" src="https://example.invalid/anh.png">');

    // The policy's refusal and the picture's own failure, in whichever order the browser tells them.
    const reported = await listed(page, 2);
    expect([...reported].sort()).toEqual([
      "failed to load https://example.invalid/anh.png",
      "img-src blocked https://example.invalid/anh.png",
    ]);
    // Chromium's word for a request its policy check ended before the network.
    expect(refused).toContain("https://example.invalid/anh.png csp");
  });

  test("reports a promise nothing caught as one error", async ({ page }) => {
    await openPage(page, script('Promise.reject(new Error("bị từ chối"));'));

    expect(await listed(page, 1)).toEqual(["Error: bị từ chối"]);
  });

  test("shows at most two thousand characters of an error of five thousand", async ({ page }) => {
    await recordPosted(page);
    await openPage(page, script('throw new Error(new Array(5001).join("x"));'));

    const [shown] = await listed(page, 1);
    expect(shown).toHaveLength(2000);
    expect(shown).toMatch(/^Uncaught Error: x+$/);
    // The page's reporter cuts the error before posting it, and the app cuts what it is sent again.
    expect(await page.evaluate(() => (window as unknown as { posted: number[] }).posted)).toEqual([2000]);
  });

  test("sends what it reported to the agent only when asked, as one message that fences it as data", async ({ page }) => {
    const { messages } = await openPage(page, script('throw new Error("hỏng");'));
    expect(await listed(page, 1)).toEqual(["Uncaught Error: hỏng"]);
    expect(messages).toEqual([]);

    await errors(page).getByRole("button", { name: pageErrors.send }).click();

    await expect(errors(page).getByRole("status")).toHaveText(pageErrors.sent(1));
    expect(messages).toHaveLength(1);
    const [sent] = messages as { text: string; canvas: unknown }[];
    expect(sent.canvas).toEqual({ artifact_id: PAGE, selection: null });
    expect(sent.text.split("\n")).toEqual([
      pageErrors.report.intro(`\`${TITLE}\``, 1),
      "",
      "```",
      "1. Uncaught Error: hỏng",
      expect.stringMatching(/^ {3}at http:\/\/127\.0\.0\.1:\d+\/api\/artifacts\/0a0b0c0d0e0f\/render:\d+:\d+$/),
      "```",
      "",
      pageErrors.report.outro,
    ]);
    await expect(page.getByTestId("message-user")).toContainText("1. Uncaught Error: hỏng");
  });
});

test.describe("a page in the canvas over the chat on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("gets most of the screen, and its errors fit a finger without a sideways scroll", async ({ page }) => {
    // A word longer than the screen is wide, which the list has to break.
    await openPage(page, script('throw new Error(new Array(301).join("x"));'));
    const [shown] = await listed(page, 1);
    expect(shown).toMatch(/^Uncaught Error: x{300}$/);

    expect(await smallTargets(page, ".canvas-dock")).toEqual([]);
    expect(await overflowing(page)).toEqual([]);
    const box = await frame(page).boundingBox();
    expect(box?.height).toBeGreaterThanOrEqual(Math.floor(844 * 0.6));
  });
});
