// Headless Chromium checks of the Structure tab's live behaviour (M3b), run by engine/tests/test_explorer_dynamic.py.
// usage: node structure_dynamic.js <explorer.html> <settings.json> [screenshot dir]
// settings.json: {"pooling_settings": [[label, params], ...]} lever settings for the Pooling recomputation.
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const file = path.resolve(process.argv[2]);
  const settings = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
  const shots = process.argv[4];
  const browser = await chromium.launch();
  const out = { console_errors: [] };
  try {
    const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 } });
    const page = await ctx.newPage();
    page.on("pageerror", (e) => out.console_errors.push(String(e)));
    page.on("console", (m) => { if (m.type() === "error") { out.console_errors.push(m.text()); } });
    await page.goto("file://" + file);
    await page.waitForSelector(".tile");
    await page.locator("#view-structure").click();
    await page.waitForSelector("#structure svg.sd-diagram .node");
    // the live state behind the drawing, recomputed in the page from the engine
    const snapshot = () => page.evaluate(() => {
      const D = JSON.parse(document.getElementById("sd-data").textContent);
      const i = Number(document.getElementById("st-time").value);
      const run = SDEngine.run(SDExplorer.params()), base = SDEngine.run(SDExplorer.baselineParams());
      const pipes = [...document.querySelectorAll("#structure svg.sd-diagram g.pipe-g")].map((g) => {
        const name = D.structure.nodes[g.getAttribute("data-flow")].name;
        return { name, rate: Number(g.getAttribute("data-rate")), want: run.series[name][i], scale: Number(g.getAttribute("data-scale")),
          width: Number(g.getAttribute("data-width")), duration: g.getAttribute("data-duration"),
          anim: getComputedStyle(g.querySelector(".pipe-flow")).animationName,
          change: g.getAttribute("data-change"), base: base.series[name][i] };
      });
      const tanks = [...document.querySelectorAll("#structure svg.sd-diagram .node.stock")].map((g) => {
        const name = g.getAttribute("data-name"), a = run.series[name], b = base.series[name];
        const mx = Math.max(...a.map(Math.abs), ...b.map(Math.abs));
        return { name, level: Number(g.getAttribute("data-level")), want: mx > 0 ? Math.abs(a[i]) / mx : 0,
          ghost: Number(g.getAttribute("data-ghost")), ghost_want: mx > 0 ? Math.abs(b[i]) / mx : 0,
          change: g.getAttribute("data-change"), cur: a[i], base: b[i] };
      });
      return { i, time: run.time[i], pipes, tanks, values: document.querySelectorAll("#structure svg.sd-diagram text.flow-value").length,
        reduced: matchMedia("(prefers-reduced-motion: reduce)").matches };
    });
    out.scrubber = await page.evaluate(() => { const s = document.getElementById("st-time"); return { min: s.min, max: s.max, value: s.value, label: document.getElementById("st-time-label").textContent }; });
    out.snap_default = await snapshot();
    // scrubber drives the chart crosshair
    await page.locator("#st-time").evaluate((s) => { s.value = "30"; s.dispatchEvent(new Event("input")); });
    await page.waitForTimeout(50);
    out.snap_30 = await snapshot();
    out.cross_after_scrub = await page.evaluate(() => [...document.querySelectorAll(".plot g.cross")].filter((g) => g.getAttribute("visibility") === "visible").length);
    out.charts = await page.locator(".chart").count();
    out.label_30 = await page.locator("#st-time-label").textContent();
    // chart crosshair drives the scrubber
    await page.locator("#view-results").click();
    await page.locator("#chart-0 .chart").focus();
    await page.keyboard.press("Home");
    for (let k = 0; k < 12; k++) { await page.keyboard.press("ArrowRight"); }
    out.scrub_after_chart = await page.locator("#st-time").inputValue();
    await page.locator("#view-structure").click();
    await page.waitForTimeout(50);
    // play and pause
    await page.locator("#st-time").evaluate((s) => { s.value = "0"; s.dispatchEvent(new Event("input")); });
    await page.locator("#st-play").click();
    await page.waitForTimeout(700);
    out.play_pressed = await page.locator("#st-play").getAttribute("aria-pressed");
    out.after_play = Number(await page.locator("#st-time").inputValue());
    await page.locator("#st-play").click();
    const paused = Number(await page.locator("#st-time").inputValue());
    await page.waitForTimeout(400);
    out.paused_stable = paused === Number(await page.locator("#st-time").inputValue());
    // flows table and delay list
    out.flow_rows = await page.locator("#flows-table tbody tr").evaluateAll((rs) => rs.map((r) => [...r.children].map((c) => c.textContent)));
    out.flow_table_check = await page.evaluate(() => {
      const i = Number(document.getElementById("st-time").value), run = SDEngine.run(SDExplorer.params());
      return [...document.querySelectorAll("#flows-table tbody tr")].every((r) => r.children[2].textContent === SDFormat.fmt(run.series[r.getAttribute("data-flow-name")][i]));
    });
    out.delays = await page.locator("#delay-list li").evaluateAll((ls) => ls.map((l) => ({ stock: l.getAttribute("data-stock"), order: l.getAttribute("data-order"),
      tau: l.getAttribute("data-tau"), text: l.textContent, curve: !!l.querySelector("svg path.response") })));
    // ripple: move a lever, then read the nodes marked changed (all variables shown)
    await page.locator("#show-all").check();
    const slider = page.locator(".lever input[type=range]").first();
    await slider.focus();
    for (let k = 0; k < 15; k++) { await slider.press("ArrowRight"); }
    await page.waitForTimeout(150);
    out.ripple_classes = await page.locator("#structure svg.sd-diagram .node.ripple").count();
    out.ripple_delays = await page.locator("#structure svg.sd-diagram .node.ripple").evaluateAll((ns) => [...new Set(ns.map((n) => n.style.animationDelay))].length);
    out.changed_nodes = await page.locator("#structure svg.sd-diagram .node[data-changed='true']").evaluateAll((ns) => ns.map((n) => n.getAttribute("data-name")).sort());
    out.ripple_params = await page.evaluate(() => SDExplorer.params());
    out.ripple_baseline = await page.evaluate(() => SDExplorer.baselineParams());
    // pooling: flags for the supplied settings (default thresholds), computed by the page's own function
    out.pooling = await page.evaluate((sets) => {
      const base = SDEngine.run(SDExplorer.baselineParams());
      return sets.map(([label, p]) => ({ label, flags: SDPooling.compute(SDEngine.run(p), base, SDPooling.defaults()) }));
    }, settings.pooling_settings);
    out.pooling_defaults = await page.evaluate(() => SDPooling.defaults());
    out.pool_panel = await page.evaluate(() => ({
      thresholds: [...document.querySelectorAll("#pooling input[type=number]")].map((e) => [e.id, e.value]),
      shares: [...document.querySelectorAll("#pool-shares li")].map((l) => l.textContent),
      levels: [...document.querySelectorAll("#pool-levels li")].map((l) => l.textContent),
      flag: (document.getElementById("pool-flag") || {}).textContent || "" }));
    // the three pooling states, read from the panel at a month where each holds in the current run
    const stateAt = async (pick) => {
      const i = await page.evaluate((pk) => {
        if (!SDPooling.defaults || !document.getElementById("th-bind")) { return -1; }
        const f = SDPooling.compute(SDEngine.run(SDExplorer.params()), SDEngine.run(SDExplorer.baselineParams()), SDPooling.defaults())[0];
        if (!f) { return -1; }
        return f.time_index.findIndex((_, k) => pk === "watch" ? f.binding_only[k] : !f.binding[k]);
      }, pick);
      if (i < 0) { return { found: false }; }
      await page.locator("#st-time").evaluate((s, v) => { s.value = String(v); s.dispatchEvent(new Event("input")); }, i);
      await page.waitForTimeout(30);
      return { found: true, i, text: await page.locator("#pool-flag").textContent(), cls: await page.locator("#pool-flag").getAttribute("class") };
    };
    out.watch_state = await stateAt("watch");
    out.clear_state = await stateAt("clear");
    // a lower binding threshold can only add flags
    if (await page.locator("#th-bind").count()) {
      await page.locator("#th-bind").fill("0.5");
      await page.locator("#th-bind").dispatchEvent("change");
    }
    out.flag_after_threshold = await page.evaluate(() => (document.getElementById("pool-flag") || {}).textContent || "");
    if (shots) {
      await page.locator("#show-all").uncheck();
      await page.locator("#zoom-fit").click();
      for (const theme of ["light", "dark"]) {
        await page.emulateMedia({ colorScheme: theme });
        await page.screenshot({ path: path.join(shots, `dynamic-${theme}.png`), fullPage: false });
      }
    }
    // reduced motion: no animation, numbers instead
    await page.emulateMedia({ reducedMotion: "reduce", colorScheme: "light" });
    await page.locator("#show-all").uncheck();
    await page.locator("#st-time").evaluate((s) => { s.value = "40"; s.dispatchEvent(new Event("input")); });
    await page.waitForTimeout(50);
    out.snap_reduced = await snapshot();
    if (shots) {
      await page.screenshot({ path: path.join(shots, `dynamic-reduced-light.png`), fullPage: false });
    }
    await ctx.close();
    const m = await (await browser.newContext({ viewport: { width: 375, height: 812 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true })).newPage();
    m.on("pageerror", (e) => out.console_errors.push(String(e)));
    await m.goto("file://" + file);
    await m.waitForSelector(".tile");
    await m.locator("#tab-structure").click();
    await m.waitForSelector("#structure svg.sd-diagram .node");
    out.mobile_scroll = await m.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
    if (shots) {
      for (const theme of ["light", "dark"]) {
        await m.emulateMedia({ colorScheme: theme });
        await m.screenshot({ path: path.join(shots, `dynamic-mobile-${theme}.png`), fullPage: true });
      }
    }
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
