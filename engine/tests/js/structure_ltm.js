// Headless checks of link and loop strength on the Structure tab (M3c), run by engine/tests/test_explorer_ltm_ui.py.
// usage: node structure_ltm.js <explorer.html> [screenshot dir]
"use strict";
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const file = path.resolve(process.argv[2]), shots = process.argv[3];
  const browser = await chromium.launch();
  const out = { console_errors: [] };
  try {
    const page = await browser.newPage({ viewport: { width: 1360, height: 900 } });
    page.on("pageerror", (e) => out.console_errors.push(String(e)));
    page.on("console", (m) => { if (m.type() === "error") { out.console_errors.push(m.text()); } });
    await page.goto("file://" + file);
    await page.waitForSelector(".tile");
    await page.locator("#view-structure").click();
    await page.waitForSelector("#structure svg.sd-diagram .node");
    const read = () => page.evaluate(() => {
      const D = JSON.parse(document.getElementById("sd-data").textContent), L = D.ltm;
      const i = Number(document.getElementById("st-time").value), month = SDEngine.run(SDExplorer.params()).time[i];
      let res;
      if (L.mode === "live") {
        res = SDLtm.compute(SDEngine.run(SDExplorer.params(), { saveper: L.dt }), SDEqs, SDEQ_META, SDEngine.META.names, L.loops);
      } else {
        const fix = (a) => (a === null ? null : a.map((x) => (x === null ? NaN : x)));
        const links = {};
        Object.keys(L.precomputed.links).forEach((k) => { links[k] = fix(L.precomputed.links[k]); });
        res = { time: L.precomputed.time, links, rel: L.precomputed.rel.map(fix) };
      }
      const j = res.time.indexOf(month);
      let mx = 0;
      Object.keys(res.links).forEach((e) => { const v = res.links[e] ? res.links[e][j] : NaN; if (isFinite(v) && Math.abs(v) < 1e300) { mx = Math.max(mx, Math.abs(v)); } });
      const links = [...document.querySelectorAll("#structure svg.sd-diagram g.lk path.link")].map((p) => {
        const g = p.parentNode, e = g.getAttribute("data-from") + ">" + g.getAttribute("data-to"), want = res.links[e] ? res.links[e][j] : NaN;
        return { e, got: p.getAttribute("data-ls"), want: isFinite(want) ? want : null, width: parseFloat(p.style.strokeWidth),
          wantWidth: 0.8 + 3.2 * (isFinite(want) && mx > 0 ? Math.abs(want) / mx : 0) };
      });
      const names = D.structure.loops.map((l) => l.name), pick = document.querySelector("input[name=dom-restrict]:checked");
      const sel = pick ? pick.value : null;
      const sub = sel === "on" ? D.structure.loops.map((l, k) => (l.nodes.some((n) => D.structure.nodes[n].name === L.restrict.stock) ? k : -1)).filter((k) => k >= 0)
        : D.structure.loops.map((_, k) => k);
      let tot = 0;
      sub.forEach((k) => { const v = res.rel[k][j]; if (isFinite(v)) { tot += Math.abs(v); } });
      // the meter shows the loop's share within the loops shown (all, or the restricted set); a loop outside that set has
      // no meter and is marked "not in this view"
      const badges = [...document.querySelectorAll("#structure svg.sd-diagram .loop-badge")].map((g) => {
        const k = D.structure.loops.findIndex((l) => l.name === g.getAttribute("data-loop-name")), want = res.rel[k][j];
        const share = sub.includes(k) && isFinite(want) && tot > 0 ? Math.abs(want) / tot : 0, mt = g.querySelector("rect.meter");
        return { name: g.getAttribute("data-loop-name"), got: g.getAttribute("data-rel"), want: isFinite(want) ? want : null,
          meter: mt ? Number(mt.getAttribute("width")) : null, wantMeter: sub.includes(k) ? 36 * share : null,
          out: g.classList.contains("outview"), wantOut: !sub.includes(k),
          title: g.querySelector("title").textContent, aria: g.getAttribute("aria-label") };
      });
      const list = [...document.querySelectorAll("#loop-list .loop-btn")].map((b) => {
        const name = b.querySelector(".loop-name").textContent, k = names.indexOf(name), o = b.querySelector(".loop-out");
        return { name, out: o ? o.textContent : null, wantOut: !sub.includes(k) };
      });
      const want = SDLtm.dominance(res.rel, res.time, sub, names, 1.0);
      const periods = [...document.querySelectorAll("#dom-periods li")].map((li) => ({ start: Number(li.getAttribute("data-start")), end: Number(li.getAttribute("data-end")), loop: li.getAttribute("data-loop") }));
      return { i, month, j, mode: L.mode, statement: document.querySelector("#dom-method p").textContent, links, badges, list, periods,
        want_periods: want, restrict: sel, now_x: (document.querySelector(".dom-now") || { getAttribute: () => null }).getAttribute("x1"),
        strongest: [...document.querySelectorAll("#dom-now li")].map((l) => l.textContent) };
    });
    // the strength panel is its own tab in the side panel, reachable without scrolling anything
    const layout = (pg) => pg.evaluate(() => {
      const side = document.querySelector(".st-side"), dom = document.getElementById("dominance"), sb = side.getBoundingClientRect();
      const chart = document.querySelector("#dom-body .dom-chart"), periods = document.getElementById("dom-periods");
      const box = dom.getBoundingClientRect(), clipped = [], overflow = [];
      dom.querySelectorAll("label, summary, h3, h4, p, li, button").forEach((e) => {
        if (!e.offsetParent) { return; }
        if (e.scrollWidth > e.clientWidth + 1) { clipped.push((e.id || e.tagName) + " " + e.textContent.slice(0, 40)); }
      });
      dom.querySelectorAll("*").forEach((e) => {
        const r = e.getBoundingClientRect();
        if (r.width > 0 && (r.right > box.right + 0.5 || r.left < box.left - 0.5)) { overflow.push((e.id || e.tagName) + " " + r.left.toFixed(1) + "-" + r.right.toFixed(1)); }
      });
      const m = document.querySelector("#dominance details.dom-method");
      return { tabs: [...document.querySelectorAll(".side-tabs [role=tab]")].map((t) => [t.textContent, t.getAttribute("aria-selected")]),
        details_hidden: document.getElementById("side-details").hidden, dom_hidden: dom.hidden, scroll_top: side.scrollTop,
        chart_visible: !!chart && chart.getBoundingClientRect().bottom <= Math.min(sb.bottom, window.innerHeight) + 0.5,
        periods_after_chart: !!periods && !!chart && periods.getBoundingClientRect().top >= chart.getBoundingClientRect().bottom,
        method_after_periods: !!m && !!periods && m.getBoundingClientRect().top >= periods.getBoundingClientRect().bottom,
        method_open: m ? m.open : null, clipped, overflow };
    });
    out.layout_default = await page.evaluate(() => ({ dom_hidden: document.getElementById("dominance").hidden,
      details_hidden: document.getElementById("side-details").hidden }));
    await page.locator("#side-tab-details").focus();
    await page.keyboard.press("ArrowRight");
    out.key_focus = await page.evaluate(() => document.activeElement.id);
    await page.waitForTimeout(50);
    out.layout = await layout(page);
    out.legend = await page.evaluate(() => [...document.querySelectorAll("#structure-legend li")].map((l) => l.textContent));
    out.base = await read();
    if (shots) {
      for (const theme of ["light", "dark"]) {
        await page.emulateMedia({ colorScheme: theme });
        await page.screenshot({ path: path.join(shots, `ltm-${theme}.png`), fullPage: false });
      }
      await page.emulateMedia({ colorScheme: "light" });
    }
    await page.locator("#st-time").evaluate((s) => { s.value = "30"; s.dispatchEvent(new Event("input")); });
    await page.waitForTimeout(50);
    out.t30 = await read();
    const slider = page.locator(".lever input[type=range]").first();
    await slider.focus();
    for (let k = 0; k < 20; k++) { await slider.press("ArrowRight"); }
    await page.waitForTimeout(150);
    out.moved = await read();
    if (await page.locator("input[name=dom-restrict]").count()) {
      await page.locator("input[name=dom-restrict][value=off]").check();
      await page.waitForTimeout(50);
      out.all_loops = await read();
    }
    const m = await (await browser.newContext({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 })).newPage();
    m.on("pageerror", (e) => out.console_errors.push(String(e)));
    await m.goto("file://" + file);
    await m.waitForSelector(".tile");
    await m.locator("#tab-structure").click();
    await m.waitForSelector("#structure svg.sd-diagram .node");
    out.mobile_scroll = await m.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
    await m.locator("#side-tab-strength").click();
    await m.waitForTimeout(50);
    out.mobile_layout = await layout(m);
    if (shots) {
      await m.evaluate(() => document.querySelector(".side-tabs").scrollIntoView());
      for (const theme of ["light", "dark"]) {
        await m.emulateMedia({ colorScheme: theme });
        await m.screenshot({ path: path.join(shots, `ltm-mobile-${theme}.png`), fullPage: false });
      }
    }
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
