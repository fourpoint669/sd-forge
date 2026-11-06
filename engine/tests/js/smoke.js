// Headless Chromium smoke test of an explorer.html (run by engine/tests/test_explorer_smoke.py).
// usage: node smoke.js <explorer.html> [screenshot dir]
// Prints one JSON object with the observations; the Python test asserts on them.
"use strict";
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const file = path.resolve(process.argv[2]);
  const shots = process.argv[3];
  const browser = await chromium.launch();
  const out = { console_errors: [], requests: [] };
  const bandCount = (p) => p.locator("#chart-0 .plot path[data-band]").count();
  const crossVisible = (p) => p.evaluate(() => [...document.querySelectorAll(".plot g.cross")].filter((g) => g.getAttribute("visibility") === "visible").length);
  try {
    const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 } });
    const page = await ctx.newPage();
    page.on("console", (m) => { if (m.type() === "error") { out.console_errors.push(m.text()); } });
    page.on("pageerror", (e) => out.console_errors.push(String(e)));
    page.on("request", (r) => { if (!r.url().startsWith("file:") && !r.url().startsWith("data:")) { out.requests.push(r.url()); } });
    await page.goto("file://" + file);
    await page.waitForSelector(".tile");
    out.title = await page.title();
    if (shots) {
      for (const theme of ["light", "dark"]) {
        await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
        await page.screenshot({ path: path.join(shots, `desktop-${theme}.png`), fullPage: true });
      }
      await page.emulateMedia({ colorScheme: "light" });
    }
    // compare-against selector: default, labels, and a switch that must move the dashed line, deltas and table together
    out.baseline_options = await page.locator("#baseline-select option").allTextContents();
    out.baseline_selected = await page.locator("#baseline-select option:checked").textContent();
    out.baseline_series_label = await page.locator("#chart-0 .legend li").evaluateAll((els) => els.map((e) => e.textContent).filter((t) => t.startsWith("Baseline:")));
    out.baseline_cmp_header = await page.locator("#compare thead th").nth(1).textContent();
    const dashed = () => page.locator("#chart-0 .plot path[stroke='var(--series-baseline)']").getAttribute("d");
    out.baseline_dashed_before = await dashed();
    out.baseline_delta_before = await page.locator(".tile.decision .tile-delta").textContent();
    const other = out.baseline_options.findIndex((t) => t !== out.baseline_selected);
    await page.locator("#baseline-select").selectOption({ index: other });
    await page.waitForTimeout(100);
    out.baseline_switched_to = await page.locator("#baseline-select option:checked").textContent();
    out.baseline_dashed_after = await dashed();
    out.baseline_delta_after = await page.locator(".tile.decision .tile-delta").textContent();
    out.baseline_cmp_header_after = await page.locator("#compare thead th").nth(1).textContent();
    out.baseline_series_label_after = await page.locator("#chart-0 .legend li").evaluateAll((els) => els.map((e) => e.textContent).filter((t) => t.startsWith("Baseline:")));
    out.baseline_consistency = await page.evaluate(() => {
      const D = JSON.parse(document.getElementById("sd-data").textContent);
      const sel = document.getElementById("baseline-select");
      const params = JSON.parse(sel.options[sel.selectedIndex].getAttribute("data-params"));
      const run = SDEngine.run(params), m = SDMetrics.all(run, D.metrics);
      const cell = [...document.querySelectorAll("#compare tbody tr")].map((r) => r.children[1].textContent);
      const want = D.metrics.map((d) => SDFormat.fmt(m[d.name]));
      const outcome = D.charts[0].vars[0];
      const path = document.querySelector("#chart-0 .plot path[stroke='var(--series-baseline)']").getAttribute("d");
      const first = path.split("L").length;
      return { cells_match: JSON.stringify(cell) === JSON.stringify(want), points: first === run.series[outcome].filter(Number.isFinite).length };
    });
    await page.locator("#baseline-select").selectOption({ index: 0 });
    await page.waitForTimeout(50);
    out.metric_labels = (await page.locator(".tile-label").allTextContents()).concat(
      await page.locator("#compare tbody th").evaluateAll((els) => els.map((e) => e.childNodes[0].textContent.replace(/ \(.*\)$/, ""))));
    out.headline_numbers = (await page.locator(".tile-value").evaluateAll((els) => els.map((e) => e.childNodes[0].textContent)))
      .concat(await page.locator("#compare tbody td .cmp-val").allTextContents())
      .concat(await page.locator("#compare tbody td:nth-child(2)").allTextContents());
    out.format_cases = await page.evaluate(() => [37e6, 542, 36, 0.108, 0.14, 999.6, 1046, 2.94e6, 0, 14.9e6].map((v) => SDFormat.fmt(v)));
    out.levers = await page.locator(".lever").count();
    out.sliders = await page.locator(".lever input[type=range]").count();
    out.outside_tags_visible_at_base = await page.locator(".tag-outside:visible").count();
    out.charts = await page.locator(".chart").count();
    out.chart_cards_about = await page.locator(".card .about-btn").count();
    out.presets = await page.locator(".preset").count();
    out.presets_pressed_at_base = await page.locator(".preset[aria-pressed=true]").allTextContents();
    out.band_note_base = await page.locator("#chart-0 .band-note").textContent();
    out.band_paths_base = await bandCount(page);
    out.band_hatched_base = await page.locator("#chart-0 .plot path[data-hatched]").count();
    out.groups_closed = await page.locator("details.grid-card:not([open])").count();
    out.groups_open = await page.locator("details.grid-card[open]").count();
    const decision = page.locator(".tile.decision .tile-value");
    out.decision_base = await decision.textContent();
    // synchronized crosshair
    await page.locator("#chart-0 .chart").focus();
    await page.keyboard.press("End");
    out.crosshairs_visible = await crossVisible(page);
    out.tooltips_visible = await page.locator(".tooltip:visible").count();
    out.tooltip_text = await page.locator("#chart-0 .tooltip").textContent();
    await page.keyboard.press("Escape");
    out.crosshairs_after_escape = await crossVisible(page);
    // move the first slider with the keyboard
    const first = page.locator(".lever input[type=range]").first();
    await first.focus();
    for (let i = 0; i < 20; i++) { await first.press("ArrowRight"); }
    await page.waitForTimeout(100);
    out.decision_moved = await decision.textContent();
    out.delta_moved = await page.locator(".tile.decision .tile-delta").textContent();
    out.band_note_moved = await page.locator("#chart-0 .band-note").textContent();
    out.band_paths_moved = await bandCount(page);
    out.band_hatched_moved = await page.locator("#chart-0 .plot path[data-hatched]").count();
    out.band_legend_moved = await page.locator("#chart-0 .legend li:has(rect)").allTextContents();
    out.presets_pressed_moved = await page.locator(".preset[aria-pressed=true]").count();
    // save scenarios
    await page.locator("#save-scenario").click();
    await page.waitForTimeout(50);
    out.saved_after_one = await page.locator(".saved-item").count();
    out.series_a_paths = await page.locator("#chart-0 .plot path[stroke='var(--series-a)']").count();
    out.end_labels = await page.locator("#chart-0 .plot text.end-label").allTextContents();
    out.compare_headers = await page.locator("#compare thead th").allTextContents();
    for (let i = 0; i < 3; i++) { await first.focus(); await first.press("PageUp"); await page.locator("#save-scenario").click(); }
    out.saved_after_four = await page.locator(".saved-item").count();
    out.save_disabled_at_four = await page.locator("#save-scenario").isDisabled();
    if (shots) {
      await page.mouse.move(0, 0);
      await page.locator("#chart-0 .chart").hover();
      for (const theme of ["light", "dark"]) {
        await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
        await page.screenshot({ path: path.join(shots, `desktop-compare-${theme}.png`), clip: { x: 0, y: 0, width: 1360, height: 1500 } });
      }
      await page.emulateMedia({ colorScheme: "light" });
    }
    await page.locator(".saved-item .remove").first().click();
    out.saved_after_remove = await page.locator(".saved-item").count();
    // typed value outside the validated range is limited while extend is off
    const num = page.locator(".lever .num input").first();
    await num.fill("999999");
    await num.press("Enter");
    await page.waitForTimeout(50);
    out.clamped_value = await num.inputValue();
    out.clamp_notice = await page.locator(".lever .notice").first().textContent();
    // extend toggle: banner, then an outside value labels every output
    await page.locator("#extend").check();
    await page.waitForTimeout(50);
    out.banner_visible = await page.locator("#banner").isVisible();
    await num.fill("999999");
    await num.press("Enter");
    await page.waitForTimeout(100);
    out.banner_text = await page.locator("#banner").textContent();
    out.outside_tags_on_tiles = await page.locator(".tile .tag-outside").count();
    out.tiles = await page.locator(".tile").count();
    out.chart_subtitles = await page.locator("#charts [id^=chart-] .card-sub").allTextContents();
    await page.locator("#extend").uncheck();
    // presets
    const presetNames = await page.locator(".preset").allTextContents();
    out.preset_names = presetNames;
    await page.locator(".preset").last().click();
    await page.waitForTimeout(100);
    out.last_preset_pressed = await page.locator(".preset").last().getAttribute("aria-pressed");
    out.band_note_last_preset = await page.locator("#chart-0 .band-note").textContent();
    await page.locator("#reset-all").click();
    await page.waitForTimeout(100);
    out.decision_reset = await decision.textContent();
    out.band_paths_reset = await bandCount(page);
    // model limits dialog, keyboard
    await page.locator("#btn-limits").click();
    out.limits_open = await page.locator("#limits-dialog").isVisible();
    out.limits_has_table = await page.locator("#limits-body table, #limits-body ul").count();
    await page.keyboard.press("Escape");
    out.limits_closed = !(await page.locator("#limits-dialog").isVisible());
    // provenance card on a chart
    await page.locator(".card .about-btn").first().click();
    out.chart_info_text = await page.locator(".card .info-card:visible").first().textContent();
    // glossary definition is labelled as explanatory text, not part of the validated model
    await page.evaluate(() => document.querySelectorAll("details.grid-card").forEach((d) => { d.open = true; }));
    await page.locator('button[aria-label="About deals won"]').first().click();
    out.glossary_card = await page.locator('[id$="-about"]:visible').last().textContent();
    await ctx.close();
    // mobile
    const mctx = await browser.newContext({ viewport: { width: 375, height: 812 }, deviceScaleFactor: 2, hasTouch: true, isMobile: true });
    const m = await mctx.newPage();
    m.on("pageerror", (e) => out.console_errors.push(String(e)));
    await m.goto("file://" + file);
    await m.waitForSelector(".tile");
    out.mobile_scroll = await m.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
    out.mobile_tabs_visible = await m.locator(".tabs").isVisible();
    out.mobile_levers_hidden = !(await m.locator("#levers").isVisible());
    out.mobile_gutter = await m.evaluate(() => getComputedStyle(document.querySelector(".layout")).paddingLeft);
    if (shots) {
      for (const theme of ["light", "dark"]) {
        await m.emulateMedia({ colorScheme: theme });
        await m.screenshot({ path: path.join(shots, `mobile-results-${theme}.png`), fullPage: true });
      }
    }
    await m.locator("#tab-levers").click();
    out.mobile_levers_shown = await m.locator("#levers").isVisible();
    out.mobile_scroll_levers = await m.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
    if (shots) {
      for (const theme of ["light", "dark"]) {
        await m.emulateMedia({ colorScheme: theme });
        await m.screenshot({ path: path.join(shots, `mobile-levers-${theme}.png`), fullPage: false });
      }
    }
    await mctx.close();
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
