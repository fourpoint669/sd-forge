// Headless Chromium checks of the Structure tab (run by engine/tests/test_explorer_structure_ui.py).
// usage: node structure_smoke.js <explorer.html> [screenshot dir]
"use strict";
const path = require("path");
const { chromium } = require("playwright");

// rendered geometry: getBBox() in each element's own coordinates, mapped to the screen with getScreenCTM()
const GEOM = `
  window.__box = function (el) {
    const b = el.getBBox(), m = el.getScreenCTM();
    const pts = [[b.x, b.y], [b.x + b.width, b.y], [b.x, b.y + b.height], [b.x + b.width, b.y + b.height]].map(([x, y]) => ({
      x: m.a * x + m.c * y + m.e, y: m.b * x + m.d * y + m.f }));
    return { l: Math.min(...pts.map((p) => p.x)), r: Math.max(...pts.map((p) => p.x)), t: Math.min(...pts.map((p) => p.y)), b: Math.max(...pts.map((p) => p.y)) };
  };
  window.__badgeLabelOverlaps = function () {
    const svg = document.querySelector("#structure svg.sd-diagram");
    const labels = [...svg.querySelectorAll(".node text.nlabel")].filter((t) => t.getBBox().width > 0).map((t) => ({ name: t.closest(".node").getAttribute("data-name"), box: window.__box(t) }));
    const badges = [...svg.querySelectorAll(".loop-badge")].map((g) => ({ name: g.getAttribute("data-loop-name"), box: window.__box(g.querySelector(".badge-bg")) }));
    const hits = [];
    badges.forEach((b) => labels.forEach((l) => {
      if (b.box.l < l.box.r && b.box.r > l.box.l && b.box.t < l.box.b && b.box.b > l.box.t) { hits.push(b.name + " x " + l.name); }
    }));
    const regions = [...svg.querySelectorAll("rect.region")].map((r) => window.__box(r));
    const titles = [...svg.querySelectorAll(".sector-toggle text")].map((t) => window.__box(t));
    const spill = titles.filter((t, i) => t.r > regions[i].r + 1).length;
    return { badges: badges.length, labels: labels.length, overlaps: hits, titles_spilling: spill };
  };
  window.__labelBoxes = function () {
    const svg = document.querySelector("#structure svg.sd-diagram");
    return [...svg.querySelectorAll(".node text.nlabel"), ...svg.querySelectorAll(".sector-toggle text")]
      .filter((t) => t.getBBox().width > 0)
      .map((t) => ({ name: t.closest(".node") ? t.closest(".node").getAttribute("data-name") : "title " + t.textContent, box: window.__box(t) }));
  };
  window.__visibleLines = function () {
    const svg = document.querySelector("#structure svg.sd-diagram");
    const vis = (e) => { for (let x = e; x && x !== svg; x = x.parentNode) { if (getComputedStyle(x).display === "none") { return false; } } return true; };
    return [...svg.querySelectorAll("path.pipe-outer, path.link, path.agg")].filter(vis);
  };
  // sample every visible line about every 3 screen pixels; report each line that enters a label or title box
  window.__samples = function (path) {
    const m = path.getScreenCTM(), L = path.getTotalLength(), n = Math.max(2, Math.ceil(L * Math.hypot(m.a, m.b) / 3)), out = [];
    for (let i = 0; i <= n; i++) {
      const p = path.getPointAtLength(L * i / n);
      out.push({ x: m.a * p.x + m.c * p.y + m.e, y: m.b * p.x + m.d * p.y + m.f });
    }
    return out;
  };
  window.__lineLabelHits = function () {
    const labels = window.__labelBoxes(), hits = new Set();
    window.__visibleLines().forEach((path) => {
      const who = path.getAttribute("class") + " " + (path.getAttribute("data-route") || "");
      window.__samples(path).forEach((p) => labels.forEach((l) => {
        if (p.x > l.box.l && p.x < l.box.r && p.y > l.box.t && p.y < l.box.b) { hits.add(who.trim() + " x " + l.name); }
      }));
    });
    return { lines: window.__visibleLines().length, labels: labels.length, hits: [...hits] };
  };
  window.__regionOverlaps = function () {
    const rs = [...document.querySelectorAll("#structure svg.sd-diagram rect.region")].map((r) => window.__box(r));
    let bad = 0;
    for (let i = 0; i < rs.length; i++) { for (let j = i + 1; j < rs.length; j++) {
      const a = rs[i], b = rs[j];
      if (a.l < b.r + 2 && b.l < a.r + 2 && a.t < b.b + 2 && b.t < a.b + 2) { bad++; }
    } }
    return { regions: rs.length, overlapping_pairs: bad };
  };
  window.__badgeOnPipe = function () {
    const svg = document.querySelector("#structure svg.sd-diagram");
    const pipes = [...svg.querySelectorAll("path.pipe-outer")].flatMap((p) => window.__samples(p));
    const hits = [];
    svg.querySelectorAll(".loop-badge").forEach((g) => {
      const b = window.__box(g.querySelector(".badge-bg"));
      if (pipes.some((p) => p.x > b.l && p.x < b.r && p.y > b.t && p.y < b.b)) { hits.push(g.getAttribute("data-loop-name")); }
    });
    return hits;
  };
  // pipes of different flows never run on top of each other (the first and last 12 user units of each segment, where it
  // joins its own mark, are not compared)
  window.__pipeOverlaps = function () {
    const svg = document.querySelector("#structure svg.sd-diagram");
    const segs = [...svg.querySelectorAll("g.pipe-g")].flatMap((g) => [...g.querySelectorAll("path.pipe-outer")].map((p) => {
      const L = p.getTotalLength(), pts = [];
      for (let d = 12; d <= L - 12; d += 3) { const q = p.getPointAtLength(d); pts.push([q.x, q.y]); }
      return { flow: g.getAttribute("data-flow"), w: parseFloat(getComputedStyle(p).strokeWidth), pts };
    }));
    const hits = new Set();
    for (let i = 0; i < segs.length; i++) { for (let j = i + 1; j < segs.length; j++) {
      const a = segs[i], b = segs[j];
      if (a.flow === b.flow) { continue; }
      // running together (an overlay) = a continuous stretch longer than twice their combined widths where the centre
      // lines stay closer than half their combined widths; a crossing at an angle is shorter and is not an overlay
      const lim = (a.w + b.w) / 2 - 0.5;
      let run = 0, worst = 0;
      a.pts.forEach((p) => {
        if (b.pts.some((q) => Math.hypot(p[0] - q[0], p[1] - q[1]) < lim)) { run += 3; worst = Math.max(worst, run); } else { run = 0; }
      });
      if (worst > 2 * (a.w + b.w)) { hits.add(a.flow + " x " + b.flow + " (" + worst + " units)"); }
    } }
    return { segments: segs.length, hits: [...hits] };
  };
  window.__geometry = function () {
    return { overlaps: window.__badgeLabelOverlaps(), lines: window.__lineLabelHits(), regions: window.__regionOverlaps(),
      badge_on_pipe: window.__badgeOnPipe(), fit: window.__fit(), pipes: window.__pipeOverlaps() };
  };
  window.__fit = function () {
    const c = document.getElementById("st-canvas").getBoundingClientRect();
    const k = window.__box(document.querySelector("#structure svg.sd-diagram g.content"));
    return { fill_w: (k.r - k.l) / c.width, fill_h: (k.b - k.t) / c.height,
      inside: k.l >= c.left - 1 && k.r <= c.right + 1 && k.t >= c.top - 1 && k.b <= c.bottom + 1 };
  };
  window.__xsec = function () {
    const vis = (e) => getComputedStyle(e).display !== "none";
    const g = [...document.querySelectorAll("#structure svg.sd-diagram g.lk.xsec")];
    return { total: g.length, visible: g.filter(vis).length,
      pipes: document.querySelectorAll("#structure svg.sd-diagram path.pipe-outer").length,
      pipes_visible: [...document.querySelectorAll("#structure svg.sd-diagram path.pipe-outer")].filter(vis).length };
  };`;
(async () => {
  const file = path.resolve(process.argv[2]);
  const shots = process.argv[3];
  const browser = await chromium.launch();
  const out = { console_errors: [], requests: [] };
  try {
    const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 } });
    const page = await ctx.newPage();
    page.on("console", (m) => { if (m.type() === "error") { out.console_errors.push(m.text()); } });
    page.on("pageerror", (e) => out.console_errors.push(String(e)));
    page.on("request", (r) => { if (!r.url().startsWith("file:") && !r.url().startsWith("data:")) { out.requests.push(r.url()); } });
    await page.goto("file://" + file);
    await page.waitForSelector(".tile");
    out.structure_hidden_by_default = !(await page.locator("#structure").isVisible());
    out.structure_svg_before_open = await page.locator("#structure svg.sd-diagram").count();
    await page.locator("#view-structure").click();
    await page.waitForSelector("#structure svg.sd-diagram .node");
    out.structure_visible = await page.locator("#structure").isVisible();
    await page.evaluate(() => { document.getElementById("st-loops").open = true; });
    out.badge_names = await page.locator("#structure svg.sd-diagram .loop-badge").evaluateAll((els) => els.map((e) => e.getAttribute("data-loop-name")).sort());
    out.badge_focusable = await page.locator("#structure svg.sd-diagram .loop-badge[tabindex='0']").count();
    out.loop_list = await page.locator("#loop-list .loop-item").count();
    out.default_node_kinds = await page.locator("#structure svg.sd-diagram .node").evaluateAll((els) => [...new Set(els.map((e) => e.getAttribute("data-kind")))].sort());
    out.legend_items = await page.locator("#structure-legend li").allTextContents();
    await page.addScriptTag({ content: GEOM });
    out.overlap_sfd_wide = await page.evaluate(() => window.__badgeLabelOverlaps());
    out.geom_sfd_wide = await page.evaluate(() => window.__geometry());
    out.fit_sfd_wide = await page.evaluate(() => window.__fit());
    out.minimap_in_canvas = await page.locator("#st-canvas svg.sd-minimap").count();
    out.minimap_closed = !(await page.locator("#minimap-wrap").evaluate((d) => d.open));
    await page.locator("#minimap-wrap summary").click();
    out.minimap_rect = await page.evaluate(() => {
      const m = document.querySelector("svg.sd-minimap").getBoundingClientRect(), c = document.getElementById("st-canvas").getBoundingClientRect();
      return { visible: m.width > 0, overlaps_canvas: m.left < c.right && m.right > c.left && m.top < c.bottom && m.bottom > c.top };
    });
    await page.locator("#minimap-wrap summary").click();
    out.xsec_default = await page.evaluate(() => window.__xsec());
    const stockWithX = await page.evaluate(() => {
      const g = document.querySelector("#structure svg.sd-diagram g.lk.xsec");
      return g ? g.getAttribute("data-from") : null;
    });
    if (stockWithX) {
      await page.locator(`#structure svg.sd-diagram .node[data-key='node:${stockWithX}']`).hover();
      out.xsec_hover = await page.evaluate(() => window.__xsec());
      await page.mouse.move(5, 5);
      await page.locator(`#structure svg.sd-diagram .node[data-key='node:${stockWithX}']`).focus();
      out.xsec_focus = await page.evaluate(() => window.__xsec());
      await page.locator("#st-canvas").focus();
    }
    out.xsec_after = await page.evaluate(() => window.__xsec());
    await page.locator("#mode-cld").click();
    await page.waitForTimeout(50);
    out.overlap_cld_wide = await page.evaluate(() => window.__badgeLabelOverlaps());
    out.geom_cld_wide = await page.evaluate(() => window.__geometry());
    out.fit_cld_wide = await page.evaluate(() => window.__fit());
    await page.locator("#mode-sfd").click();
    await page.waitForTimeout(50);
    if (shots) {
      for (const theme of ["light", "dark"]) {
        await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
        await page.screenshot({ path: path.join(shots, `structure-default-${theme}.png`), fullPage: false });
      }
      await page.emulateMedia({ colorScheme: "light" });
    }
    // show all variables
    await page.locator("#show-all").check();
    await page.waitForTimeout(50);
    out.nodes_all = await page.locator("#structure svg.sd-diagram .node").count();
    out.node_ids_all = await page.locator("#structure svg.sd-diagram .node").evaluateAll((els) => els.map((e) => e.getAttribute("data-name")).sort());
    out.nodes_focusable = await page.locator("#structure svg.sd-diagram .node[tabindex='0']").count();
    out.delay_marks = await page.locator("#structure svg.sd-diagram .delay-mark").evaluateAll((els) => els.map((e) => e.getAttribute("data-delay-stock") + "|" + e.getAttribute("data-order") + "|" + e.getAttribute("data-tau")).sort());
    out.link_styles = await page.locator("#structure svg.sd-diagram path.link").evaluateAll((els) => {
      const c = {};
      els.forEach((e) => { const k = e.getAttribute("data-sign") + "|" + (e.getAttribute("stroke-dasharray") || "solid"); c[k] = (c[k] || 0) + 1; });
      return c;
    });
    out.sign_glyphs = await page.locator("#structure svg.sd-diagram text.sign").count();
    out.links_drawn = await page.locator("#structure svg.sd-diagram path.link").count();
    if (shots) {
      for (const theme of ["light", "dark"]) {
        await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
        await page.screenshot({ path: path.join(shots, `structure-all-${theme}.png`), fullPage: false });
      }
      await page.emulateMedia({ colorScheme: "light" });
    }
    // focus mode with the keyboard
    const cust = page.locator("#structure svg.sd-diagram .node[data-name='Customers']");
    await cust.focus();
    await page.keyboard.press("Enter");
    await page.waitForTimeout(50);
    out.focus_title = await page.locator("#structure-detail h3").first().textContent();
    out.focus_dimmed = await page.locator("#structure svg.sd-diagram .node.dim").count();
    out.focus_lit = await page.locator("#structure svg.sd-diagram .node.lit").count();
    out.focus_loops_listed = await page.locator("#structure-detail .detail-loops li").count();
    if (shots) {
      for (const theme of ["light", "dark"]) {
        await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
        await page.screenshot({ path: path.join(shots, `structure-focus-${theme}.png`), fullPage: false });
      }
      await page.emulateMedia({ colorScheme: "light" });
    }
    await page.keyboard.press("Escape");
    out.focus_cleared = await page.locator("#structure svg.sd-diagram .node.dim").count();
    // loop isolation
    const firstBadge = page.locator("#structure svg.sd-diagram .loop-badge").first();
    out.first_badge_name = await firstBadge.getAttribute("data-loop-name");
    await firstBadge.focus();
    await page.keyboard.press("Enter");
    await page.waitForTimeout(50);
    out.isolated_edges = await page.locator("#structure svg.sd-diagram path.loop-halo").count();
    out.xsec_isolated_hidden_on_loop = await page.evaluate(() => {
      const vis = (e) => getComputedStyle(e).display !== "none";
      return [...document.querySelectorAll("#structure svg.sd-diagram g.lk.xsec.on-loop")].filter((g) => !vis(g)).length;
    });
    out.isolated_title = await page.locator("#structure-detail h3").first().textContent();
    if (shots) {
      for (const theme of ["light", "dark"]) {
        await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
        await page.screenshot({ path: path.join(shots, `structure-loop-${theme}.png`), fullPage: false });
      }
      await page.emulateMedia({ colorScheme: "light" });
    }
    await page.locator("#structure-clear").click();
    out.isolation_cleared = await page.locator("#structure svg.sd-diagram path.loop-halo").count();
    // search
    await page.locator("#structure-search").fill("churn");
    out.search_results = await page.locator("#search-results button").allTextContents();
    await page.locator("#search-results button").first().click();
    await page.waitForTimeout(50);
    out.search_focus_title = await page.locator("#structure-detail h3").first().textContent();
    await page.keyboard.press("Escape");
    // sector collapse
    const sectorBtn = page.locator("#structure svg.sd-diagram .sector-toggle").first();
    out.sector_name = await sectorBtn.getAttribute("data-sector");
    const before = await page.locator("#structure svg.sd-diagram .node").count();
    await sectorBtn.focus();
    await page.keyboard.press("Enter");
    await page.waitForTimeout(50);
    out.collapse_hidden = before - (await page.locator("#structure svg.sd-diagram .node").count());
    out.collapse_expanded_attr = await page.locator("#structure svg.sd-diagram .sector-toggle").first().getAttribute("aria-expanded");
    await page.locator("#structure svg.sd-diagram .sector-toggle").first().press("Enter");
    // zoom and minimap
    const vb0 = await page.locator("#structure svg.sd-diagram").getAttribute("viewBox");
    await page.locator("#zoom-in").click();
    out.zoom_changed = vb0 !== (await page.locator("#structure svg.sd-diagram").getAttribute("viewBox"));
    out.minimap = await page.locator("#structure svg.sd-minimap rect.viewport").count();
    // CLD mode
    await page.locator("#mode-cld").click();
    await page.waitForTimeout(50);
    out.cld_tanks = await page.locator("#structure svg.sd-diagram .tank").count();
    out.cld_badges = await page.locator("#structure svg.sd-diagram .loop-badge").count();
    if (shots) {
      await page.locator("#zoom-fit").click();
      for (const theme of ["light", "dark"]) {
        await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
        await page.screenshot({ path: path.join(shots, `structure-cld-${theme}.png`), fullPage: false });
      }
    }
    await ctx.close();
    // mobile
    const mctx = await browser.newContext({ viewport: { width: 375, height: 812 }, deviceScaleFactor: 2, hasTouch: true, isMobile: true });
    const m = await mctx.newPage();
    m.on("pageerror", (e) => out.console_errors.push(String(e)));
    await m.goto("file://" + file);
    await m.waitForSelector(".tile");
    await m.locator("#tab-structure").click();
    await m.waitForSelector("#structure svg.sd-diagram .node");
    out.mobile_structure_visible = await m.locator("#structure").isVisible();
    await m.addScriptTag({ content: GEOM });
    out.overlap_sfd_narrow = await m.evaluate(() => window.__badgeLabelOverlaps());
    out.geom_sfd_narrow = await m.evaluate(() => window.__geometry());
    out.fit_sfd_narrow = await m.evaluate(() => window.__fit());
    await m.locator("#mode-cld").click();
    await m.waitForTimeout(50);
    out.overlap_cld_narrow = await m.evaluate(() => window.__badgeLabelOverlaps());
    out.geom_cld_narrow = await m.evaluate(() => window.__geometry());
    await m.locator("#mode-sfd").click();
    await m.waitForTimeout(50);
    out.mobile_scroll = await m.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
    if (shots) {
      for (const theme of ["light", "dark"]) {
        await m.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
        await m.screenshot({ path: path.join(shots, `structure-mobile-${theme}.png`), fullPage: true });
      }
    }
    await mctx.close();
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
