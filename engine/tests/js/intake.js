// Headless check of the /sd-explorer intake on a built page, run by engine/tests/test_explorer_intake.py.
// usage: node intake.js <explorer.html>
"use strict";
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const file = path.resolve(process.argv[2]);
  const browser = await chromium.launch();
  const out = { console_errors: [] };
  try {
    const page = await browser.newPage({ viewport: { width: 1360, height: 900 } });
    page.on("pageerror", (e) => out.console_errors.push(String(e)));
    page.on("console", (m) => { if (m.type() === "error") { out.console_errors.push(m.text()); } });
    await page.goto("file://" + file);
    await page.waitForFunction(() => document.querySelector(".tile") || document.querySelector("#structure svg .node"));
    await page.waitForTimeout(300);
    out.first = await page.evaluate(() => ({
      results_hidden: document.getElementById("results").hidden, structure_hidden: document.getElementById("structure").hidden,
      sliders: [...document.querySelectorAll(".lever input[type=range]")].length,
      held: [...document.querySelectorAll(".lever-meta")].filter((m) => m.textContent.includes("held at its base value")).length,
      closed_groups: [...document.querySelectorAll("details.grid-card")].filter((d) => !d.open).length,
      baseline: document.getElementById("baseline-select").selectedOptions[0].textContent,
      compare_header: [...document.querySelectorAll("#compare th")].map((t) => t.textContent).join(" | "),
      headline_first: (document.querySelector(".tile") || {}).textContent }));
    await page.locator("#btn-limits").click();
    await page.waitForSelector("#limits-dialog[open]");
    out.limits = await page.evaluate(() => ({
      heading: (document.querySelector("#limits-intake h3") || {}).textContent || null,
      note: (document.querySelector("#limits-intake p") || {}).textContent || null,
      items: [...document.querySelectorAll("#intake-settings li")].map((li) => ({ text: li.textContent, source: li.getAttribute("data-source") })),
      verbatim_first: document.getElementById("limits-body").textContent.length > 0 }));
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
