import { expect, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { overflowing } from "./canvas-overflow";
import { composer, frame, html, inside, openPage, PAGE, script } from "./render-page";

/**
 * Who has the keyboard while a page an agent wrote runs beside the conversation. A page may focus
 * itself whenever it likes; only a pointer the person presses inside it, or Tab, gives it the
 * keyboard to keep. Which window the keys go to is the browser's doing, so only a browser shows it.
 */

const { page: words } = vi.canvas;

/** What has the focus in the app: `IFRAME` while the page has the keyboard, `BODY` while nothing has. */
const holder = (page: Page) => page.evaluate(() => document.activeElement?.tagName);
/** The line that says the keys typed now go to the page. */
const marker = (page: Page) => page.getByText(words.keyboard);

/** Thirty keys a person types. */
const TYPED = "the quick brown fox jumps over";

const count = (id: string) => `var at = document.getElementById("${id}"); at.textContent = String(Number(at.textContent) + 1);`;

/** A page with a field of its own, which shows the keys it heard and how often the keyboard left it. */
const LISTENING = [
  '<input id="field" autofocus>',
  '<p id="heard"></p>',
  '<p id="left">0</p>',
  script(
    [
      'document.addEventListener("keydown", function (event) { document.getElementById("heard").textContent += event.key; });',
      `window.addEventListener("blur", function () { ${count("left")} });`,
    ].join("\n"),
  ),
].join("\n");

/** Where the frame and the word over it are laid out. */
async function laidOut(page: Page) {
  const [around, word] = [await frame(page).boundingBox(), await marker(page).boundingBox()];
  if (around === null || word === null) throw new Error("the page or the word over it is not laid out");
  return { around, word };
}

/** The line drawn around the page: its style and how wide it is. */
const edge = (page: Page) =>
  frame(page).evaluate((shown) => {
    const { outlineStyle, outlineWidth } = getComputedStyle(shown);
    return outlineStyle === "none" ? "none" : `${outlineStyle} ${outlineWidth}`;
  });

/** What a page's reporter takes for a press: the pointer going down and coming up, each also as the mouse the browser makes of it. */
const PRESS_KINDS = ["pointerdown", "mousedown", "pointerup", "mouseup"];

/** The page presses its own field and lets it go again, down to the click that comes of it, as a script can and no person did. */
const pressItself = (page: Page) =>
  inside(page)
    .locator("#field")
    .evaluate((field, kinds) => {
      for (const kind of [...kinds, "click"]) {
        const made = { bubbles: true, composed: true, detail: 1 };
        field.dispatchEvent(kind.startsWith("pointer") ? new PointerEvent(kind, { ...made, isPrimary: true }) : new MouseEvent(kind, made));
      }
    }, PRESS_KINDS);

/** How long a person holds the button of a mouse down in a click: well past the time a page is waited on. */
const HELD_MS = 150;

/** A button of the page that keeps the browser from moving the focus when it is pressed. */
const BUTTON = '<button id="go" style="display: block; width: 200px; height: 80px">go</button>';
const KEEPS = 'document.getElementById("go").addEventListener("mousedown", function (event) { event.preventDefault(); });';

/** The person presses the page's button and holds it down. */
async function pressAndHold(page: Page) {
  const at = await inside(page).locator("#go").boundingBox();
  if (at === null) throw new Error("the button of the page is not laid out");
  await page.mouse.move(at.x + at.width / 2, at.y + at.height / 2);
  await page.mouse.down();
}

/** The page takes the keyboard for the field it has, as a script of its own would. */
const grab = (page: Page) =>
  inside(page)
    .locator("body")
    .evaluate(() => {
      window.focus();
      document.getElementById("field")?.focus();
    });

/** A page that goes on taking the keyboard for its button, which the keys meant for the message then press. */
const TAKING = 'setInterval(function () { window.focus(); document.getElementById("go").focus(); }, 100);';

/** What a page can have every event in it say of itself: each is read off a prototype the page may write to. */
const DRESSED = {
  "a pointer made it": 'Object.defineProperty(UIEvent.prototype, "detail", { get: function () { return 1; } });',
  "it is a pointer coming up": 'Object.defineProperty(Event.prototype, "type", { get: function () { return "pointerup"; } });',
};

/** The person goes on pressing Enter for the message: the page is stopped all the same, and the keys after it are the message's. */
async function entersUntilStopped(page: Page) {
  const stopped = page.getByText(words.grabbing);
  for (let key = 0; key < 150 && !(await stopped.isVisible()); key++) await page.keyboard.press("Enter");

  await expect(stopped).toBeVisible();
  await expect(frame(page)).toHaveCount(0);
  await page.keyboard.type(TYPED);
  await expect(composer(page)).toHaveValue(TYPED);
}

test.describe("the keyboard beside a page in the canvas", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("goes to the page with a click in it and stays there, however often the person goes back and forth", async ({ page }) => {
    await openPage(page, LISTENING);

    // One time more than a page may take the keyboard unasked: what the person does is never counted.
    for (let round = 1; round <= 6; round++) {
      await composer(page).click();
      await expect(marker(page)).toHaveCount(0);
      await inside(page).locator("#field").click();
      // Typed straight after the click and on for longer than the page is waited on: a keyboard
      // taken back in between would send the rest of the keys to the message.
      await page.keyboard.type("abcdefghij", { delay: 30 });

      await expect(inside(page).locator("#heard")).toHaveText("abcdefghij".repeat(round));
      // The keyboard left the page as often as the person took it away, and not once more.
      await expect(inside(page).locator("#left")).toHaveText(String(round - 1));
      await expect(marker(page)).toBeVisible();
    }

    await expect(composer(page)).toHaveValue("");
    await expect(frame(page)).toHaveCount(1);
    await expect(page.getByText(words.grabbing)).toHaveCount(0);
  });

  test("is shown to be with the page by a line around it and a word over it, which move nothing and let the pointer through", async ({ page }) => {
    const pressed = `window.addEventListener("pointerdown", function () { ${count("presses")} });`;
    await openPage(page, `${LISTENING}<p id="presses">0</p>${script(pressed)}`);
    await composer(page).click();
    const before = await frame(page).boundingBox();
    expect(await edge(page)).toBe("none");

    await inside(page).locator("#field").click();
    await expect(marker(page)).toBeVisible();

    const { around, word } = await laidOut(page);
    expect(around).toEqual(before);
    expect(await edge(page)).toBe("solid 2px");
    expect(word.x).toBeGreaterThan(around.x + around.width / 2);
    expect(word.x + word.width).toBeLessThan(around.x + around.width);
    expect(word.y).toBeGreaterThan(around.y);
    expect(word.y + word.height).toBeLessThan(around.y + around.height / 2);

    // A press on the word is a press on the page under it.
    await page.mouse.click(word.x + word.width / 2, word.y + word.height / 2);
    await expect(inside(page).locator("#presses")).toHaveText("2");
    await expect(marker(page)).toBeVisible();

    await composer(page).click();
    await expect(marker(page)).toHaveCount(0);
    expect(await edge(page)).toBe("none");
    expect(await frame(page).boundingBox()).toEqual(before);
  });

  test("stays with a message being written when the page focuses itself", async ({ page }) => {
    await openPage(page, LISTENING);
    await composer(page).click();

    await grab(page);

    // The page saw the keyboard leave it again: from here on no key can be on its way to it.
    await expect(inside(page).locator("#left")).toHaveText("1");
    await page.keyboard.type(TYPED);
    await expect(composer(page)).toHaveValue(TYPED);
    await expect(inside(page).locator("#heard")).toHaveText("");
    await expect(page.getByText(words.grabbing)).toHaveCount(0);
  });

  test("goes to a page that takes it at the click, however long the person held the button and however often", async ({ page }) => {
    const atTheClick = 'document.getElementById("go").addEventListener("click", function () { document.getElementById("field").focus(); });';
    await openPage(page, LISTENING + BUTTON + script(`${KEEPS}\n${atTheClick}`));

    // One time more than a page may take the keyboard unasked.
    for (let round = 1; round <= 6; round++) {
      await composer(page).click();
      await pressAndHold(page);
      await page.waitForTimeout(HELD_MS);
      // The press moved nothing, and what it offered is long over: only its end offers again.
      expect(await holder(page)).toBe("TEXTAREA");
      await page.mouse.up();
      await page.keyboard.type("abcdefghij", { delay: 30 });

      await expect(inside(page).locator("#heard")).toHaveText("abcdefghij".repeat(round));
      await expect(inside(page).locator("#left")).toHaveText(String(round - 1));
      await expect(marker(page)).toBeVisible();
    }

    await expect(composer(page)).toHaveValue("");
    await expect(frame(page)).toHaveCount(1);
    await expect(page.getByText(words.grabbing)).toHaveCount(0);
  });

  test("stays with the message when the page takes it while the button is still held, long after the press", async ({ page }) => {
    const later = `document.getElementById("go").addEventListener("mousedown", function () { setTimeout(function () { document.getElementById("field").focus(); }, ${HELD_MS}); });`;
    await openPage(page, LISTENING + BUTTON + script(`${KEEPS}\n${later}`));
    await composer(page).click();

    for (let press = 1; press <= 4; press++) {
      await pressAndHold(page);
      // The page had the keyboard and saw it go again, with the button down all the while.
      await expect(inside(page).locator("#left")).toHaveText(String(press));
      await page.keyboard.type(String(press));
      await page.mouse.up();
      expect(await holder(page)).toBe("TEXTAREA");
    }
    await pressAndHold(page);

    // Each of the five was held against the page.
    await expect(page.getByText(words.grabbing)).toBeVisible();
    await expect(frame(page)).toHaveCount(0);
    await page.mouse.up();
    await page.keyboard.type("5");
    await expect(composer(page)).toHaveValue("12345");
  });

  test("stays with the message when the keys meant for it press a button of a page that goes on taking it", async ({ page }) => {
    // Enter on a button is a click the browser vouches for, and a page that took the keyboard gets
    // the keys typed while it is waited on. No pointer went down or came up for it: it is no press.
    await openPage(page, BUTTON + script(TAKING));
    await composer(page).click();

    await entersUntilStopped(page);
  });

  for (const [said, dressing] of Object.entries(DRESSED)) {
    test(`stays with the message when that page has the click those keys make say ${said}`, async ({ page }) => {
      // The browser vouches for who made an event and for nothing else it says: the rest is read
      // off a prototype, which the page wrote to before it took the keyboard.
      await openPage(page, BUTTON + script(`${dressing}\n${TAKING}`));
      await composer(page).click();

      await entersUntilStopped(page);
    });
  }

  test("stays with the message when the page makes up a press of its own before it takes it", async ({ page }) => {
    const made = PRESS_KINDS.map((kind) => `window.addEventListener("${kind}", function () { ${count("presses")} });`).join("\n");
    await openPage(page, `${LISTENING}<p id="presses">0</p>${script(made)}`);
    await composer(page).click();

    await pressItself(page);
    // The page heard the press it made from beginning to end, as it would one of the person's.
    await expect(inside(page).locator("#presses")).toHaveText(String(PRESS_KINDS.length));
    await grab(page);

    await expect(inside(page).locator("#left")).toHaveText("1");
    await page.keyboard.type(TYPED);
    await expect(composer(page)).toHaveValue(TYPED);
    await expect(inside(page).locator("#heard")).toHaveText("");
    await expect(marker(page)).toHaveCount(0);
  });

  test("is not kept by a page that takes it while nothing in the app holds it", async ({ page }) => {
    await openPage(page, LISTENING);
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    expect(await holder(page)).toBe("BODY");

    await grab(page);

    // There is no element to give it back to: it is taken off the frame, and the page saw it go.
    await expect(inside(page).locator("#left")).toHaveText("1");
    await page.keyboard.type(TYPED);
    await expect(inside(page).locator("#heard")).toHaveText("");
    expect(await holder(page)).toBe("BODY");
  });

  test("stays with the message when the page takes it as the pointer passes over", async ({ page }) => {
    const taking = 'window.addEventListener("pointermove", function () { window.focus(); document.getElementById("field").focus(); });';
    await openPage(page, LISTENING + script(taking));
    await composer(page).click();
    await page.keyboard.type("một ");

    await frame(page).hover();
    await expect(inside(page).locator("#left")).toHaveText("1");
    await composer(page).hover();
    await page.keyboard.type("hai");

    await expect(composer(page)).toHaveValue("một hai");
    await expect(inside(page).locator("#heard")).toHaveText("");
    expect(await holder(page)).toBe("TEXTAREA");
  });

  test("stays with the message while the wheel turned over the page scrolls the page", async ({ page }) => {
    await openPage(page, '<div style="height: 4000px">Dài</div>');
    await composer(page).click();
    await page.keyboard.type("một ");

    await frame(page).hover();
    await page.mouse.wheel(0, 600);

    await expect.poll(() => inside(page).locator("body").evaluate(() => window.scrollY)).toBeGreaterThan(0);
    await page.keyboard.type("hai");
    await expect(composer(page)).toHaveValue("một hai");
  });

  test("goes to the page with Tab", async ({ page }) => {
    await openPage(page, LISTENING);
    await composer(page).click();

    // Tab by Tab through the app's controls, until the one that goes into the page.
    for (let presses = 0; presses < 60 && (await holder(page)) !== "IFRAME"; presses++) await page.keyboard.press("Tab");
    await page.keyboard.type("ab", { delay: 100 });

    await expect(inside(page).locator("#heard")).toHaveText("ab");
    expect(await holder(page)).toBe("IFRAME");
    await expect(marker(page)).toBeVisible();
    await expect(page.getByText(words.grabbing)).toHaveCount(0);
  });

  test("stays with the message when the page takes it after Tab pressed with Control, which goes through none of the app's controls", async ({ page }) => {
    await openPage(page, LISTENING);
    await composer(page).click();

    await page.keyboard.press("Control+Tab");
    expect(await holder(page)).toBe("TEXTAREA");
    await grab(page);

    await expect(inside(page).locator("#left")).toHaveText("1");
    await page.keyboard.type(TYPED);
    await expect(composer(page)).toHaveValue(TYPED);
    await expect(inside(page).locator("#heard")).toHaveText("");
  });

  test("stays where the person had it while a page that goes on taking it is stopped", async ({ page }) => {
    const grabbing = `<input autofocus>${script("setInterval(function () { window.focus(); }, 100);")}`;
    const { fake } = await openPage(page, grabbing);
    await composer(page).click();

    await expect(page.getByText(words.grabbing)).toBeVisible();
    await expect(frame(page)).toHaveCount(0);
    // Nothing is clicked again: the thirty keys go where the person was writing.
    await page.keyboard.type(TYPED);
    await expect(composer(page)).toHaveValue(TYPED);

    // The agent has written the page again by the time the person asks for it.
    fake.write(PAGE, html("<p>Đã yên</p>"));
    await page.getByRole("button", { name: words.reload, exact: true }).click();

    await expect(inside(page).getByText("Đã yên")).toBeVisible();
    await expect(page.getByText(words.grabbing)).toHaveCount(0);
    // The button that was pressed is gone: the focus is on the box of the page, not on nothing.
    expect(await page.evaluate(() => document.activeElement?.className)).toBe("canvas-frame-box");
  });

  test("is not given to a page that wrote itself anew, whose presses nothing vouches for", async ({ page }) => {
    // `document.open()` takes every listener off the page's window, the reporter's among them.
    const anew = [
      'window.addEventListener("load", function () { setTimeout(function () {',
      "  document.open();",
      "  document.write('<input id=\"field\"><p id=\"heard\"></p>');",
      '  document.addEventListener("keydown", function (event) { document.getElementById("heard").textContent += event.key; });',
      "}, 0); });",
    ].join("\n");
    await openPage(page, script(anew));
    await expect(inside(page).locator("#field")).toBeVisible();
    await composer(page).click();

    for (let press = 1; press <= 4; press++) {
      await inside(page).locator("#field").click();
      await expect.poll(() => holder(page)).toBe("TEXTAREA");
      await page.keyboard.type(String(press));
    }
    await inside(page).locator("#field").click();

    await expect(page.getByText(words.grabbing)).toBeVisible();
    await expect(frame(page)).toHaveCount(0);
    await page.keyboard.type("5");
    await expect(composer(page)).toHaveValue("12345");
  });
});

test.describe("the keyboard beside a page on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("goes to the page with the first tap, which the page hears as a pointer pressed", async ({ page }) => {
    const tapped = `window.addEventListener("pointerdown", function () { ${count("taps")} });`;
    await openPage(page, `${LISTENING}<p id="taps">0</p>${script(tapped)}`);
    const before = await frame(page).boundingBox();

    await inside(page).locator("#field").tap();
    await expect(inside(page).locator("#taps")).toHaveText("1");
    await page.keyboard.type("abcdefghij", { delay: 30 });

    await expect(inside(page).locator("#heard")).toHaveText("abcdefghij");
    await expect(inside(page).locator("#left")).toHaveText("0");
    await expect(marker(page)).toBeVisible();
    await expect(page.getByText(words.grabbing)).toHaveCount(0);

    // The word that says so is over the page: nothing moved for it, and nothing scrolls sideways.
    const { around, word } = await laidOut(page);
    expect(around).toEqual(before);
    expect(word.x).toBeGreaterThanOrEqual(around.x);
    expect(word.x + word.width).toBeLessThanOrEqual(around.x + around.width);
    expect(await overflowing(page)).toEqual([]);
  });
});
