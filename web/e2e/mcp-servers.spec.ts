import { expect, test, type Page } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeMcp, SIGN_IN_LOCAL_ONLY, mcpServer, mcpTool, unknownServer } from "../src/test/fake-mcp";
import { coachAgent, defaultAgent, mockApi } from "./mock-api";
import { smallTargets } from "./small-targets";

const t = vi.mcp;
const master = { ...defaultAgent, name: "Trợ lý", delegates: ["coach"] };
const SAVE = { name: "Lưu", exact: true } as const;
const TOOLS = [
  mcpTool("notion", "search", { description: "Tìm trang trong Notion", requires_approval: false, read_only_hint: true }),
  mcpTool("notion", "create-pages", { description: "Tạo trang mới" }),
];

const row = (page: Page, name = "notion") => page.getByTestId("mcp-card").getByTestId(`mcp-server-${name}`);
const status = (page: Page, name = "notion") => row(page, name).getByTestId("mcp-status");

/** The authorization server: the person agrees there and is sent back, as the crew's own
 *  callback sends them, to a page that loads from nothing and reads the list again. */
async function authorizationServer(page: Page, mcp: FakeMcp, baseURL: string) {
  const visits: string[] = [];
  await page.route("https://auth.example.test/**", async (route) => {
    visits.push(route.request().url());
    mcp.signedIn("notion", TOOLS);
    const back = `${baseURL}/#/manage/connections`;
    await route.fulfill({ contentType: "text/html", body: `<script>location.replace(${JSON.stringify(back)})</script>` });
  });
  return visits;
}

test("a server that wants a sign-in is signed in to from Connections, used, and signed out of", async ({ page, baseURL }) => {
  const mcp = new FakeMcp([mcpServer({ status: "signed_out", description: "Ghi chú của nhà" })]);
  await mockApi(page, { agents: [{ ...master, mcp: ["notion"] }, coachAgent], mcp });
  const visits = await authorizationServer(page, mcp, baseURL!);
  await page.goto("/#/manage/connections");

  await expect(status(page)).toHaveText(t.status.signed_out);
  await expect(row(page)).toContainText("https://mcp.notion.com/mcp");
  await expect(row(page)).toContainText("Ghi chú của nhà");
  await expect(row(page)).toContainText(t.signInHint);
  await expect(row(page).getByTestId("mcp-agents")).toHaveText(vi.connectionsPage.usedBy("default"));
  await expect(row(page).getByRole("button", { name: t.signOut })).toHaveCount(0);

  // Opened from another machine the crew refuses, and the page says so in its words.
  mcp.refuseSignIn = SIGN_IN_LOCAL_ONLY;
  await row(page).getByRole("button", { name: t.signIn }).click();
  await expect(row(page).getByTestId("mcp-note")).toHaveText(vi.connectionsPage.failed(SIGN_IN_LOCAL_ONLY));
  expect(visits).toEqual([]);
  await expect(status(page)).toHaveText(t.status.signed_out);

  // On the machine itself the person is sent out to agree, and comes back signed in.
  await row(page).getByRole("button", { name: t.signIn }).click();
  await expect(status(page)).toHaveText(t.status.connected);
  expect(visits).toEqual(["https://auth.example.test/authorize?server=notion"]);
  await expect(page).toHaveURL(/#\/manage\/connections$/);
  await expect(row(page)).toContainText(t.signedIn);
  await expect(row(page).getByRole("button", { name: t.signIn })).toHaveCount(0);
  await expect(row(page).getByTestId("mcp-note")).toHaveCount(0);

  // What the server offers, and which of it asks first.
  await row(page).getByText(t.tools(2)).click();
  const search = row(page).getByTestId("mcp-tool-search");
  await expect(search).toContainText("Tìm trang trong Notion");
  await expect(search).toContainText(t.runsFreely);
  await expect(search).toContainText(t.saysReadOnly);
  await expect(row(page).getByTestId("mcp-tool-create-pages")).toContainText(t.asksFirst);

  // The agent it is switched on for holds the tools; the other is told why it does not.
  await page.goto("/#/manage/tools");
  const tool = page.getByTestId("tool-row").filter({ hasText: "mcp__notion__create_pages" });
  await expect(tool).toContainText(vi.tools.fromServer("notion"));
  await expect(tool.getByLabel(vi.tools.legendOn)).toHaveCount(1);
  await expect(tool.getByLabel(vi.tools.legendMcpOff)).toHaveCount(1);

  await page.goto("/#/manage/connections");
  await expect(status(page)).toHaveText(t.status.connected);
  page.once("dialog", (dialog) => {
    expect(dialog.message()).toBe(t.confirmSignOut("notion"));
    void dialog.accept();
  });
  await row(page).getByRole("button", { name: t.signOut }).click();
  await expect(status(page)).toHaveText(t.status.signed_out);
  await expect(row(page).getByTestId("mcp-note")).toHaveText(t.signedOut);
  await expect(row(page)).not.toContainText(t.signedIn);
  await expect(row(page).getByText(t.tools(2))).toHaveCount(0);
  await expect(row(page).getByRole("button", { name: t.signIn })).toBeVisible();
});

test("a server that is down says why, and is tried again from its row", async ({ page }) => {
  const mcp = new FakeMcp([mcpServer({ status: "failed", error: "notion: HTTP 503" }), mcpServer({ name: "wiki" })]);
  await mockApi(page, { agents: [master], mcp });
  await page.goto("/#/manage/connections");

  await expect(status(page)).toHaveText(t.status.failed);
  await expect(row(page).getByTestId("mcp-error")).toHaveText("notion: HTTP 503");
  await expect(row(page).getByTestId("mcp-agents")).toHaveText(t.noAgents);
  await expect(status(page, "wiki")).toHaveText(t.status.connected);

  // Still down: the row keeps its reason, and no note claims otherwise.
  const again = page.waitForRequest((r) => r.method() === "POST" && /\/api\/mcp\/notion\/reconnect$/.test(r.url()));
  await row(page).getByRole("button", { name: t.reconnect }).click();
  await again;
  await expect(row(page).getByRole("button", { name: t.reconnect })).toBeEnabled();
  await expect(status(page)).toHaveText(t.status.failed);
  await expect(row(page).getByTestId("mcp-error")).toHaveText("notion: HTTP 503");
  await expect(row(page).getByTestId("mcp-note")).toHaveCount(0);

  mcp.becomes("notion", { status: "connected", error: "", tools: TOOLS });
  await row(page).getByRole("button", { name: t.reconnect }).click();
  await expect(status(page)).toHaveText(t.status.connected);
  await expect(row(page).getByTestId("mcp-error")).toHaveCount(0);
  await expect(row(page)).toContainText(t.tools(2));
});

test("a server still being tried is watched until it has an answer, with nothing clicked", async ({ page }) => {
  const mcp = new FakeMcp([mcpServer({ status: "idle" })]);
  await mockApi(page, { agents: [master], mcp });
  await page.goto("/#/manage/connections");
  await expect(status(page)).toHaveText(t.status.idle);

  mcp.servers = [mcpServer({ status: "connected", tools: TOOLS })];

  await expect(status(page)).toHaveText(t.status.connected, { timeout: 8_000 });
  await expect(row(page)).toContainText(t.tools(2));
});

test("saving the key a server's header reads brings the server up without a reload", async ({ page }) => {
  const key = { name: "WIKI_TOKEN", group: "mcp", secret: true, url: false, present: false, source: null, checkable: false, editable: true, servers: ["wiki"] };
  const mcp = new FakeMcp([mcpServer({ name: "wiki", url: "https://wiki.example.test/mcp", status: "failed", error: "wiki: HTTP 401", uses_key: true, env: ["WIKI_TOKEN"] })]);
  mcp.becomes("wiki", { status: "connected", error: "" });
  await mockApi(page, { agents: [master], mcp, credentials: [key] });
  await page.goto("/#/manage/connections");

  const card = page.getByTestId("mcp-card");
  await expect(row(page, "wiki")).toContainText(t.usesKey);
  await expect(status(page, "wiki")).toHaveText(t.status.failed);
  await expect(card.getByText(t.keys)).toBeVisible();
  const variable = card.getByTestId("credentials-mcp").getByTestId("credential-WIKI_TOKEN");
  await expect(variable).toContainText(vi.connectionsPage.usedByServers("wiki"));

  await variable.getByRole("button", { name: "Đặt" }).click();
  await variable.getByLabel("Giá trị cho WIKI_TOKEN").fill("wiki-secret-123");
  await variable.getByRole("button", { name: "Lưu" }).click();

  await expect(status(page, "wiki")).toHaveText(t.status.connected);
  await expect(row(page, "wiki").getByTestId("mcp-error")).toHaveCount(0);
  await expect(page.getByTestId("connections")).not.toContainText("wiki-secret-123");
});

test("an agent is handed a server in its editor, and a server the file dropped has to come off first", async ({ page }) => {
  const mcp = new FakeMcp([mcpServer({ description: "Ghi chú của nhà", tools: TOOLS })]);
  await mockApi(page, { agents: [master, { ...coachAgent, mcp: ["old"] }], mcp });
  await page.goto("/#/manage/crew/coach");
  const editor = page.getByTestId("agent-editor");
  const picker = editor.getByTestId("mcp-picker");

  const notion = picker.getByRole("listitem").filter({ hasText: "notion" });
  await expect(notion).toContainText(t.status.connected);
  await expect(notion).toContainText("Ghi chú của nhà");
  await expect(notion).toContainText(t.tools(2));
  const old = picker.getByRole("listitem").filter({ hasText: "old" });
  await expect(old).toContainText(vi.editor.mcpGone);
  await expect(old.getByRole("checkbox")).toBeChecked();
  // A server's tools are not in the allow-list: they come with the server.
  await expect(editor.getByTestId("tool-picker")).not.toContainText("mcp__notion");

  await notion.getByRole("checkbox").check();
  await editor.getByRole("button", SAVE).click();
  await expect(editor).toContainText(vi.editor.saveFailed(unknownServer("old")));
  await expect(notion.getByRole("checkbox")).toBeChecked();

  // A click, not `uncheck`: the row goes with its tick, so there is no box left to read.
  await old.getByRole("checkbox").click();
  await expect(old).toHaveCount(0);
  const patch = page.waitForRequest((r) => r.method() === "PATCH" && /\/api\/agents\/coach$/.test(r.url()));
  await editor.getByRole("button", SAVE).click();
  expect((await patch).postDataJSON()).toEqual({ profile: { mcp: ["notion"] } });
  await expect(editor.getByRole("button", SAVE)).toBeDisabled();
  // A server is handed over on the spot: nothing asks for a restart.
  await expect(editor.getByTestId("restart-banner")).toHaveCount(0);

  await page.reload();
  await expect(page.getByTestId("mcp-picker").getByRole("checkbox")).toBeChecked();
  await page.goto("/#/manage/connections");
  await expect(row(page).getByTestId("mcp-agents")).toHaveText(vi.connectionsPage.usedBy("coach"));
});

/** Boxes under `within` whose content reaches past their own edge: text with nowhere to
 *  break. A box further out may clip what spills, so the page's own width does not show it. */
const spills = (page: Page, within: string) =>
  page.evaluate((within) => {
    const found: string[] = [];
    for (const el of document.querySelectorAll<HTMLElement>(`${within}, ${within} *`)) {
      if (el.clientWidth === 0 || el.scrollWidth <= el.clientWidth + 1) continue;
      found.push(`${el.tagName.toLowerCase()}.${String(el.className).split(" ")[0]} ${el.scrollWidth}>${el.clientWidth}`);
    }
    return found;
  }, within);

/** Badges under `within` squeezed onto more than one line by what stands beside them. */
const squeezedBadges = (page: Page, within: string) =>
  page.evaluate((within) => {
    const badges = [...document.querySelectorAll<HTMLElement>(`${within} .badge`)];
    const tall = badges.filter((el) => el.getBoundingClientRect().height > 1.5 * parseFloat(getComputedStyle(el).lineHeight));
    return tall.map((el) => (el.textContent ?? "").trim());
  }, within);

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  // Nothing in these breaks on its own: no space, and no hyphen a line could end after.
  const LONG = "https://selfhostedknowledgebaseofthewholehouseholdandtheneighbours.example.test/workspaces/home/mcp";
  const WIKI = "wiki_of_the_whole_household_2026";
  const QUERY = "query_every_data_source_of_the_whole_workspace_at_once";
  const servers = () => [
    mcpServer({
      status: "signed_out",
      signed_in: true,
      error: "notion: phiên đăng nhập đã hết hạn và không gia hạn được",
      tools: [...TOOLS, mcpTool("notion", QUERY, { description: LONG, read_only_hint: true })],
      skipped: ["search", "fetch"],
    }),
    mcpServer({ name: WIKI, url: LONG, status: "failed", error: `wiki: không gọi được ${LONG}`, uses_key: true }),
  ];

  test("the MCP card fits the screen and every control on it is big enough to tap", async ({ page }) => {
    await mockApi(page, { agents: [{ ...master, mcp: ["notion"] }, coachAgent], mcp: new FakeMcp(servers()) });
    await page.goto("/#/manage/connections");
    const card = page.getByTestId("mcp-card");
    await card.scrollIntoViewIfNeeded();
    await expect(status(page)).toHaveText(t.status.signed_out);
    await row(page).getByText(t.tools(3)).click();
    await expect(row(page).getByTestId(`mcp-tool-${QUERY}`)).toBeVisible();

    expect(await smallTargets(page, '[data-testid="mcp-card"]')).toEqual([]);
    for (const name of ["notion", WIKI]) {
      const box = (await row(page, name).boundingBox())!;
      expect(box.x, name).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width, name).toBeLessThanOrEqual(390);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    // A long address, name or reason goes onto the next line, and a badge beside a long
    // name moves below it whole rather than being squeezed.
    expect(await spills(page, '[data-testid="mcp-card"]')).toEqual([]);
    expect(await squeezedBadges(page, '[data-testid="mcp-card"]')).toEqual([]);
  });

  test("the MCP boxes of an agent fit the screen and are big enough to tap", async ({ page }) => {
    await mockApi(page, { agents: [master, { ...coachAgent, mcp: ["old-server-the-file-dropped"] }], mcp: new FakeMcp(servers()) });
    await page.goto("/#/manage/crew/coach");
    const picker = page.getByTestId("agent-editor").getByTestId("mcp-picker");
    await picker.scrollIntoViewIfNeeded();
    await expect(picker.getByRole("listitem")).toHaveCount(3);

    expect(await smallTargets(page, '[data-testid="mcp-picker"]')).toEqual([]);
    const box = (await picker.boundingBox())!;
    expect(box.x + box.width).toBeLessThanOrEqual(390);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  });
});
