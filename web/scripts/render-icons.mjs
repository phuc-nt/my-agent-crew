// Draws the installed-app icons from public/favicon.svg, so the tab, the home screen and
// the sidebar mark stay one picture. Run `npm run icons` after changing the SVG and commit
// the PNGs it writes; the build only copies them.
//
// Two shapes come out of one drawing. "any" keeps the rounded tile with clear corners.
// "Full" fills the square edge to edge, for the platforms that cut their own shape out of
// it: iOS rounds the apple-touch icon itself, and Android crops a maskable icon to
// whatever the launcher uses. The glyph already sits inside the maskable safe circle.
import { readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const publicDir = join(dirname(fileURLToPath(import.meta.url)), "..", "public");
const rounded = await readFile(join(publicDir, "favicon.svg"), "utf8");
const full = rounded.replace('rx="9"', 'rx="0"');

const icons = [
  { file: "icon-192.png", size: 192, svg: rounded },
  { file: "icon-512.png", size: 512, svg: rounded },
  { file: "icon-maskable-512.png", size: 512, svg: full },
  { file: "apple-touch-icon.png", size: 180, svg: full },
];

const browser = await chromium.launch();
try {
  for (const { file, size, svg } of icons) {
    const page = await browser.newPage({ viewport: { width: size, height: size } });
    const src = `data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`;
    await page.setContent(
      `<style>html,body{margin:0;background:transparent}img{display:block}</style>` +
        `<img src="${src}" width="${size}" height="${size}">`,
    );
    await page.locator("img").evaluate((img) => img.decode());
    await writeFile(join(publicDir, file), await page.screenshot({ omitBackground: true }));
    await page.close();
    console.log(`wrote ${file}`);
  }
} finally {
  await browser.close();
}
