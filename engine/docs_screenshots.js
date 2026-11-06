// Annotated screenshot for docs/QUICKSTART.md, taken from a real explorer.html (run by engine/build_docs.py --screenshots).
// usage: node engine/docs_screenshots.js <explorer.html> <out.png>
// Numbered markers are placed at the bounding boxes of real page elements; nothing on the page is changed otherwise.
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");
const { chromium } = require("playwright");

// [number, selector, side]: side l = left of the element, r = right of it (markers never sit on the element's text)
const MARKERS = {
  results: [[1, "#levers-title", "r"], [2, "#presets-title", "r"], [3, "#baseline-select", "r"], [4, "#headline", "l"],
    [5, "#btn-limits", "l"], [6, "#scen-title", "r"]],
  details: [[7, "#st-time-label", "r"], [8, "#st-canvas", "l"], [9, "#pooling", "l"]],
  strength: [[10, "#side-tab-strength", "r"], [11, "#dom-body .dom-chart", "l"], [12, "#structure svg.sd-diagram .loop-badge[data-loop-name^='R8 ']", "r"]],
};

async function mark(page, list, clipLeft) {
  await page.evaluate(([items, minLeft]) => {
    items.forEach(([n, sel, side]) => {
      const el = document.querySelector(sel);
      if (!el) { throw new Error("marker target missing: " + sel); }
      const r = el.getBoundingClientRect(), m = document.createElement("div");
      let right = r.right;
      if (side === "r" && el.firstChild && el.firstChild.nodeType === 3) {   // text element: right of its text, not its box
        const rg = document.createRange();
        rg.selectNodeContents(el);
        right = rg.getBoundingClientRect().right;
      }
      const left = side === "r" ? right + 10 : Math.max(minLeft + 2, r.left - 36);
      m.textContent = String(n);
      m.setAttribute("style", "position:fixed;z-index:99999;pointer-events:none;width:30px;height:30px;border-radius:15px;" +
        "background:#111;color:#fff;font:700 16px/30px system-ui,sans-serif;text-align:center;box-shadow:0 0 0 3px #fff,0 0 0 5px #111;" +
        "left:" + left + "px;top:" + Math.max(4, r.top + Math.min(r.height / 2, 20) - 15) + "px");
      document.body.appendChild(m);
    });
  }, [list, clipLeft || 0]);
}

(async () => {
  const file = path.resolve(process.argv[2]), out = path.resolve(process.argv[3]);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "sd-docs-"));
  const browser = await chromium.launch();
  try {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1, colorScheme: "light", reducedMotion: "reduce" });
    const page = await ctx.newPage();
    await page.goto("file://" + file);
    await page.waitForSelector(".tile");
    await mark(page, MARKERS.results);
    await page.screenshot({ path: path.join(tmp, "a.png"), clip: { x: 0, y: 0, width: 1280, height: 720 } });
    await page.goto("file://" + file);
    await page.waitForSelector(".tile");
    await page.locator("#view-structure").click();
    await page.waitForSelector("#structure svg.sd-diagram .node");
    await page.locator("#st-play").scrollIntoViewIfNeeded();
    await page.evaluate(() => window.scrollTo(0, document.getElementById("st-play").getBoundingClientRect().top + window.scrollY - 70));
    const side = await page.evaluate(() => Math.ceil(document.getElementById("levers").getBoundingClientRect().right) + 1);
    await mark(page, MARKERS.details, side);
    await page.screenshot({ path: path.join(tmp, "b.png"), clip: { x: side, y: 0, width: 1280 - side, height: 800 } });
    await page.evaluate(() => document.querySelectorAll("body > div[style*='z-index:99999']").forEach((m) => m.remove()));
    await page.locator("#side-tab-strength").click();
    await page.waitForSelector("#dom-body .dom-chart");
    await mark(page, MARKERS.strength, side);
    await page.screenshot({ path: path.join(tmp, "c.png"), clip: { x: side, y: 0, width: 1280 - side, height: 800 } });
    // one image: the three panels with their titles
    const img = (f) => "data:image/png;base64," + fs.readFileSync(path.join(tmp, f)).toString("base64");
    const html = `<!doctype html><meta charset="utf-8"><style>body{margin:0;background:#fff;font:600 22px system-ui,sans-serif;color:#111}
      section{padding:14px 18px 6px}h2{font-size:22px;margin:0 0 8px}img{display:block;max-width:1280px;border:1px solid #888}</style>
      <section><h2>A. Results tab (markers 1-6)</h2><img src="${img("a.png")}"></section>
      <section><h2>B. Structure tab, Details side tab (markers 7-9)</h2><img src="${img("b.png")}"></section>
      <section><h2>C. Structure tab, Loop strength side tab (markers 10-12)</h2><img src="${img("c.png")}"></section>`;
    const cp = await (await browser.newContext({ viewport: { width: 1318, height: 800 }, deviceScaleFactor: 1 })).newPage();
    await cp.setContent(html);
    await cp.screenshot({ path: out, fullPage: true });
  } finally {
    await browser.close();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
