// Screenshot a URL with Puppeteer and save into ./temporary screenshots/.
// Usage:
//   node screenshot.mjs http://localhost:3002
//   node screenshot.mjs http://localhost:3002 label     -> screenshot-N-label.png
// Files auto-increment (screenshot-1.png, screenshot-2.png, ...) and are never overwritten.
import puppeteer from "puppeteer";
import { mkdir, readdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL(".", import.meta.url));
const OUT_DIR = join(ROOT, "temporary screenshots");

const url = process.argv[2] || "http://localhost:3002";
const label = process.argv[3] ? `-${process.argv[3]}` : "";

const [vw, vh] = (process.env.VIEWPORT || "1440x900").split("x").map(Number);

async function nextIndex() {
  await mkdir(OUT_DIR, { recursive: true });
  const files = await readdir(OUT_DIR);
  let max = 0;
  for (const f of files) {
    const m = f.match(/^screenshot-(\d+)/);
    if (m) max = Math.max(max, Number(m[1]));
  }
  return max + 1;
}

const n = await nextIndex();
const outPath = join(OUT_DIR, `screenshot-${n}${label}.png`);

const browser = await puppeteer.launch({
  headless: "new",
  args: ["--no-sandbox", "--disable-setuid-sandbox"],
});
try {
  const page = await browser.newPage();
  await page.setViewport({ width: vw || 1440, height: vh || 900, deviceScaleFactor: 2 });
  await page.goto(url, { waitUntil: "networkidle0", timeout: 60000 });

  await page.evaluate(async () => {
    await new Promise((resolve) => {
      let y = 0;
      const step = window.innerHeight * 0.6;
      const timer = setInterval(() => {
        window.scrollBy(0, step);
        y += step;
        if (y >= document.body.scrollHeight) {
          clearInterval(timer);
          window.scrollTo(0, 0);
          resolve();
        }
      }, 120);
    });
  });
  await new Promise((r) => setTimeout(r, 700));

  const fullPage = process.env.FULL !== "0";
  if (!fullPage) {
    const hash = new URL(url).hash;
    if (hash) {
      await page.evaluate((h) => {
        const el = document.querySelector(h);
        if (el) el.scrollIntoView({ block: "start" });
      }, hash);
      await new Promise((r) => setTimeout(r, 400));
    }
  }
  const buf = await page.screenshot({ fullPage });
  await writeFile(outPath, buf);
  console.log(`saved -> ${outPath}`);
} finally {
  await browser.close();
}
