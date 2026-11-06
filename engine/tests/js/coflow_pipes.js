// One flow can drain two stocks (a coflow: a sale leaves the vehicle inventory and the prospect pool). The pipe used to
// keep only the first source, so the other stock was drawn with that drain missing. Every source must now be drawn.
"use strict";
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const b = await chromium.launch();
  try {
    let checked = 0;
    for (const name of ["bass-b2b-adoption", "saas-churn-vs-winrate", "car-dealership-profit"]) {
      const page = await b.newPage({ viewport: { width: 1440, height: 900 } });
      await page.goto("file://" + path.resolve(__dirname, "../../../projects", name, "explorer.html"));
      await page.waitForSelector(".tile");
      const S = await page.evaluate(() => JSON.parse(document.getElementById("sd-data").textContent).structure);
      const multi = S.pipes.filter((p) => p.from.length > 1);
      if (!multi.length) { await page.close(); continue; }
      await page.locator("#view-structure").click();
      await page.waitForSelector("#structure svg.sd-diagram .node");
      for (const p of multi) {
        checked++;
        const seen = await page.evaluate((a) => {
          const svg = document.querySelector("#structure svg.sd-diagram");
          // only a source that is actually on screen gets an inlet (a collapsed sector hides its stocks)
          const shown = a.froms.filter((id) => !!svg.querySelector('[data-key="node:' + id + '"]'));
          const g = svg.querySelector('g.pipe-g[data-flow="' + a.flow + '"]');
          if (!g) { return null; }
          const inner = [...g.querySelectorAll("path.pipe-inner")];
          const key = (el) => el.getAttribute("d");
          return {
            shown: shown,
            inlets: inner.filter((el) => !el.getAttribute("marker-end")).map(key),
            outlets: inner.filter((el) => el.getAttribute("marker-end")).map(key),
          };
        }, { flow: p.flow, froms: p.from });
        const where = name + " flow " + p.flow;
        if (seen === null) { throw new Error(where + ": no pipe group was drawn"); }
        if (seen.shown.length < 2) {
          throw new Error(where + ": fewer than two of its source stocks are on screen, so this view does not test a coflow");
        }
        if (seen.inlets.length !== seen.shown.length) {
          throw new Error(where + " drains " + seen.shown.length + " stocks on screen (" + seen.shown.join(", ") + ") but "
            + seen.inlets.length + " inlet pipes were drawn");
        }
        if (seen.outlets.length > p.to.length) {
          throw new Error(where + " fills " + p.to.length + " stocks but " + seen.outlets.length + " outlets were drawn");
        }
        if (new Set(seen.inlets).size !== seen.inlets.length) {
          throw new Error(where + ": two inlet pipes follow the same path, so one stock's drain is invisible");
        }
        for (const d of seen.inlets.concat(seen.outlets)) {
          if (!d || d.length < 8) { throw new Error(where + ": a pipe segment has no usable path (" + d + ")"); }
        }
      }
      await page.close();
    }
    if (!checked) { throw new Error("no shipped project has a flow that drains two stocks: this regression is untested"); }
    console.log("coflow pipes checked: " + checked);
  } finally { await b.close(); }
})().catch((e) => { console.error(e.message || e); process.exit(1); });
