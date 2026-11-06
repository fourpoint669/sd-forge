// sd-explorer page logic. Every number shown comes from SDEngine runs or from the embedded validated files.
(function () {
  "use strict";
  var D = JSON.parse(document.getElementById("sd-data").textContent);
  var VARS = D.variables;
  var TU = D.time_unit;
  var state = {params: Object.assign({}, D.base), extend: false};
  // Compare against: every preset (validation.toml [[policies]]); the one equal to the model's base values says so, and
  // "base values" is added when no preset equals them. Default: the first policy (gate 8 measures lift against it).
  var BASELINES = D.presets.map(function (p) {
    var isBase = sameParams(p.params, D.base);
    return {name: p.name === "base" && isBase ? "base values" : p.name + (isBase ? " (= base values)" : ""), params: p.params};
  });
  if (!BASELINES.some(function (b) { return sameParams(b.params, D.base); })) {
    BASELINES.push({name: "base values", params: D.base});
  }
  // default baseline: the intake's choice (explorer_intake.toml) by preset name, or "base values" = the entry whose
  // parameters equal the base (a preset where one equals it, else the added entry). Unresolved -> say so, never guess.
  var baseline = BASELINES[0];
  if (D.baseline_default) {
    var hit = BASELINES.filter(function (b, i) {
      return D.baseline_default === "base values" ? sameParams(b.params, D.base) : (D.presets[i] && D.presets[i].name === D.baseline_default);
    })[0];
    if (hit) { baseline = hit; } else {
      console.error("baseline '" + D.baseline_default + "' from the intake matches no preset; showing " + baseline.name);
    }
  }
  var baseRun = SDEngine.run(baseline.params);
  var baseMetrics = SDMetrics.all(baseRun, D.metrics);
  function baselineLabel() { return "Baseline: " + baseline.name; }
  var leverUI = {};
  var quickUI = {};
  var pending = false;

  function $(id) { return document.getElementById(id); }
  function h(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text !== undefined && text !== null) { e.textContent = text; }
    return e;
  }

  // ---------- number formatting ----------
  function trimNum(x, sig) { return String(Number(x.toPrecision(sig))); }
  // One rule for every number read off the page: 3 significant figures, trailing zeros kept, K / M / B above a thousand
  // (37.0M, 542, 36.0, 0.108, 1.00K). A value that rounds up to 1000 moves to the next unit.
  var UNITS = [[1e9, "B"], [1e6, "M"], [1e3, "K"], [1, ""]];
  function fmt(v) {
    if (typeof v !== "number" || isNaN(v)) { return "undefined"; }
    if (!isFinite(v)) { return v > 0 ? "never (∞)" : "−∞"; }
    var a = Math.abs(v);
    if (a === 0) { return "0.00"; }
    if (a < 1e-3) { return v.toExponential(2); }
    for (var i = 0; i < UNITS.length; i++) {
      if (a >= UNITS[i][0] || i === UNITS.length - 1) {
        var t = (v / UNITS[i][0]).toPrecision(3);
        if (Math.abs(parseFloat(t)) >= 1000 && i > 0) { t = (v / UNITS[i - 1][0]).toPrecision(3); return t + UNITS[i - 1][1]; }
        return t + UNITS[i][1];
      }
    }
  }
  // axis ticks are round numbers: compact, without padding zeros
  function fmtAxis(v) {
    var a = Math.abs(v);
    if (a >= 1e9) { return trimNum(v / 1e9, 3) + "B"; }
    if (a >= 1e6) { return trimNum(v / 1e6, 3) + "M"; }
    if (a >= 1e4) { return trimNum(v / 1e3, 3) + "K"; }
    if (a >= 100) { return Math.round(v).toLocaleString("en-US"); }
    return a === 0 ? "0" : trimNum(v, 3);
  }
  // Typed numbers: a comma is a thousands separator only in a proper grouping ("1,000", "12,345", "1,234,567", Indian "1,00,000");
  // any other single comma is a decimal comma ("0,14", "1,5", "0,125"); anything else with a comma is not a number.
  function parseTyped(text) {
    var t = String(text).trim();
    if (/^[+-]?[1-9]\d{0,2}(,\d{3})+(\.\d+)?$/.test(t) || /^[+-]?[1-9]\d?(,\d{2})+,\d{3}(\.\d+)?$/.test(t)) { return t.replace(/,/g, ""); }
    if (/^[+-]?\d*,\d+$/.test(t)) { return t.replace(",", "."); }
    return t;
  }
  function fmtLever(v) { return String(Number(v.toPrecision(6))); }
  function leverStep(l) {
    var span = l.high - l.low;
    return span > 0 ? Math.pow(10, Math.floor(Math.log10(span)) - 2) : 1;
  }
  function snap(v, step) { return Number((Math.round(v / step) * step).toPrecision(12)); }

  function unitText(u) { return u === "Dmnl" ? "dimensionless" : u; }

  // ---------- lever ranges ----------
  function isOutside(l, v) { return v < l.low || v > l.high; }
  function anyOutside() {
    return D.levers.some(function (l) { return isOutside(l, state.params[l.name]); });
  }
  function bounds(l) {
    if (!state.extend) { return [l.low, l.high]; }
    var span = l.high - l.low, lo = l.low - span, hi = l.high + span;
    var d = l.domain || [null, null];
    if (d[0] !== null) { lo = Math.max(lo, d[0]); }
    if (d[1] !== null) { hi = Math.min(hi, d[1]); }
    return [lo, hi];
  }
  function hardBounds(l) {
    if (!state.extend) { return [l.low, l.high]; }
    var d = l.domain || [null, null];
    return [d[0] === null ? -Infinity : d[0], d[1] === null ? Infinity : d[1]];
  }

  // ---------- tags & info cards ----------
  function shortTag(conf) { return String(conf).split(/[\s(]/)[0]; }
  function tagEl(text, cls, title) {
    var t = h("span", "tag" + (cls ? " " + cls : ""), text);
    if (title) { t.title = title; }
    return t;
  }
  function infoCard(name) {
    var m = VARS[name], card = h("div", "info-card"), dl = h("dl");
    function row(k, v) { if (v === null || v === undefined || v === "") { return; } dl.appendChild(h("dt", null, k)); dl.appendChild(h("dd", null, v)); }
    if (m.definition_source === "glossary") { row("Explanation (glossary, not part of the validated model)", m.definition); }
    else { row("Definition", m.definition); }
    row("Equation", m.equation);
    row("Unit", m.unit);
    if (m.range) { row("Validated range", fmtLever(m.range[0]) + " to " + fmtLever(m.range[1]) + " " + m.unit); }
    if (m.domain) {
      row("Allowed domain", (m.domain[0] === null ? "−∞" : fmtLever(m.domain[0])) + " to " +
        (m.domain[1] === null ? "∞" : fmtLever(m.domain[1])));
    }
    if (m.base !== undefined) { row("Base value", fmtLever(m.base) + " " + m.unit); }
    row("Source", m.source);
    row("Confidence", m.confidence + (m.illustrative ? "; illustrative input, replace with your own figure" : ""));
    card.appendChild(dl);
    return card;
  }

  // ---------- lever panel ----------
  function buildLevers() {
    var root = $("lever-groups");
    var bySector = {};
    D.levers.forEach(function (l) { (bySector[l.sector] = bySector[l.sector] || []).push(l); });
    var order = D.sectors.filter(function (s) { return bySector[s]; });
    if (bySector.other) { order.push("other"); }
    order.forEach(function (sec) {
      var fs = h("div", "sector"), hd = h("h3", "sector-title", sec);
      hd.id = "sector-" + order.indexOf(sec);
      fs.setAttribute("role", "group");
      fs.setAttribute("aria-labelledby", hd.id);
      fs.appendChild(hd);
      bySector[sec].forEach(function (l) { fs.appendChild(leverRow(l)); });
      root.appendChild(fs);
    });
  }

  function leverRow(l) {
    var m = VARS[l.name], id = "lv-" + D.levers.indexOf(l);
    var row = h("div", "lever");
    var top = h("div", "lever-top");
    var info = h("button", "btn btn-quiet", "About");
    info.type = "button";
    info.setAttribute("aria-expanded", "false");
    info.setAttribute("aria-label", "About " + l.name);
    var card = infoCard(l.name);
    card.hidden = true;
    card.id = id + "-info";
    info.setAttribute("aria-controls", card.id);
    info.addEventListener("click", function () {
      card.hidden = !card.hidden;
      info.setAttribute("aria-expanded", String(!card.hidden));
    });
    var meta = h("div", "lever-meta");
    meta.appendChild(tagEl(shortTag(m.confidence), null, "Confidence: " + m.confidence + ". Source: " + m.source));
    if (m.illustrative) { meta.appendChild(tagEl("illustrative", "tag-illustrative", "Illustrative input: replace with your own figure")); }
    var ui = {l: l, row: row};
    if (l.fixed || l.exposed === false) {
      top.appendChild(h("span", "name", l.name));
      top.appendChild(info);
      row.appendChild(top);
      var fixed = h("div", "lever-meta");
      ui.fixedValue = h("span", "fixed-value", fmtLever(state.params[l.name]));
      fixed.appendChild(ui.fixedValue);
      fixed.appendChild(h("span", "unit", unitText(l.unit)));
      fixed.appendChild(h("span", null, l.fixed ? "· fixed in validation; changed only by presets" :
        "· held at its base value on this page (levers chosen at intake: see Model limits); changed only by presets"));
      row.appendChild(fixed);
    } else {
      var lab = h("label", null, l.name);
      lab.htmlFor = id;
      top.appendChild(lab);
      top.appendChild(info);
      row.appendChild(top);
      var ctrl = h("div", "lever-ctrl");
      var range = h("input");
      range.type = "range";
      range.id = id;
      range.step = String(leverStep(l));
      range.setAttribute("aria-describedby", id + "-meta");
      var numWrap = h("span", "num");
      var num = h("input");
      num.type = "text";
      num.inputMode = "decimal";
      num.setAttribute("aria-label", l.name + " value in " + l.unit);
      num.setAttribute("aria-describedby", id + "-meta");
      numWrap.appendChild(num);
      var reset = h("button", "btn reset");
      reset.type = "button";
      reset.innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M3 8a5 5 0 1 0 1.6-3.7" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><path d="M3 2.5v3h3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
      reset.setAttribute("aria-label", "Reset " + l.name + " to base " + fmtLever(l.base));
      ctrl.appendChild(range);
      ctrl.appendChild(numWrap);
      ctrl.appendChild(reset);
      row.appendChild(ctrl);
      meta.id = id + "-meta";
      meta.insertBefore(h("span", "unit", unitText(l.unit)), meta.firstChild);
      ui.rangeText = h("span", null, "validated " + fmtLever(l.low) + "–" + fmtLever(l.high));
      meta.insertBefore(ui.rangeText, meta.childNodes[1]);
      ui.outsideTag = tagEl("outside validated range", "tag-outside");
      ui.outsideTag.hidden = true;
      meta.appendChild(ui.outsideTag);
      ui.notice = h("p", "notice");
      ui.notice.setAttribute("role", "status");
      ui.range = range; ui.num = num; ui.reset = reset;
      range.addEventListener("input", function () { setLever(l, snap(Number(range.value), leverStep(l)), "slider"); });
      range.addEventListener("keydown", function (e) {
        if (e.key !== "PageUp" && e.key !== "PageDown") { return; }
        e.preventDefault();
        var b = bounds(l), d = (b[1] - b[0]) / 10 * (e.key === "PageUp" ? 1 : -1);
        setLever(l, snap(Math.min(b[1], Math.max(b[0], state.params[l.name] + d)), leverStep(l)), "slider");
      });
      num.addEventListener("change", function () { commitNumber(l); });
      num.addEventListener("keydown", function (e) { if (e.key === "Enter") { commitNumber(l); } });
      reset.addEventListener("click", function () { setLever(l, l.base, "reset"); });
    }
    row.appendChild(meta);
    if (ui.notice) { row.appendChild(ui.notice); }
    row.appendChild(card);
    leverUI[l.name] = ui;
    return row;
  }

  function buildQuickControls() {
    var preferred = VARS["total programme budget"] ? ["total programme budget", "base annual churn rate"] :
      VARS["floorplan rate"] ? ["floorplan rate", "new gross per vehicle"] : ["marketing reach rate", "win rate"];
    var eligible = D.levers.filter(function (l) { return !l.fixed && l.exposed !== false; });
    var chosen = preferred.map(function (name) { return eligible.filter(function (l) { return l.name === name; })[0]; }).filter(Boolean);
    eligible.forEach(function (l) { if (chosen.length < 2 && chosen.indexOf(l) < 0) { chosen.push(l); } });
    var root = $("quick-controls");
    root.appendChild(h("h2", null, "Explore the decision"));
    chosen.forEach(function (l, i) {
      var row = h("div", "quick-control"), label = h("label", null, l.name), id = "quick-" + i;
      label.htmlFor = id;
      var value = h("output", "quick-value"); value.setAttribute("for", id);
      var range = h("input"); range.type = "range"; range.id = id; range.step = String(leverStep(l));
      range.setAttribute("aria-describedby", "lv-" + D.levers.indexOf(l) + "-meta");
      range.addEventListener("input", function () { setLever(l, snap(Number(range.value), leverStep(l)), "slider"); });
      var reset = h("button", "btn quick-reset", "Reset"); reset.type = "button";
      reset.setAttribute("aria-label", "Reset primary control " + l.name + " to base");
      reset.addEventListener("click", function () { setLever(l, l.base, "reset"); });
      var status = h("span", "quick-status");
      row.appendChild(label); row.appendChild(value); row.appendChild(range); row.appendChild(reset); row.appendChild(status);
      quickUI[l.name] = {row: row, range: range, value: value, reset: reset, status: status}; root.appendChild(row);
    });
  }

  function commitNumber(l) {
    var ui = leverUI[l.name], raw = parseTyped(ui.num.value), v = Number(raw);
    if (raw === "" || !isFinite(v)) {
      ui.notice.textContent = "Not a number; kept " + fmtLever(state.params[l.name]) + ".";
      syncLever(l);
      return;
    }
    if (raw === fmtLever(state.params[l.name])) { return; }  // Enter then change: the second commit changes nothing
    var hb = hardBounds(l), c = Math.min(hb[1], Math.max(hb[0], v));
    ui.notice.textContent = c !== v ? (state.extend ? "Limited to the model's allowed domain: " : "Limited to the validated range: ") + fmtLever(c) + "." : "";
    setLever(l, c, "number");
  }

  var pendingRipple = null;
  function leverNode(name) {
    var ids = Object.keys(D.structure.nodes).filter(function (k) { return D.structure.nodes[k].name === name; });
    return ids.length ? ids[0] : null;
  }
  function setLever(l, v, source) {
    state.params[l.name] = v;
    pendingRipple = l.name;
    if (source !== "number") { leverUI[l.name].notice.textContent = ""; }
    syncLever(l);
    schedule();
  }

  function syncLever(l) {
    var ui = leverUI[l.name], v = state.params[l.name];
    if (ui.fixedValue) { ui.fixedValue.textContent = fmtLever(v); return; }
    var b = bounds(l);
    ui.range.min = String(b[0]);
    ui.range.max = String(b[1]);
    ui.range.value = String(v);
    ui.range.setAttribute("aria-valuetext", fmtLever(v) + " " + l.unit + (isOutside(l, v) ? ", outside validated range" : ""));
    ui.num.value = fmtLever(v);
    if (quickUI[l.name]) {
      var q = quickUI[l.name];
      q.range.min = ui.range.min; q.range.max = ui.range.max; q.range.value = ui.range.value;
      q.range.setAttribute("aria-valuetext", ui.range.getAttribute("aria-valuetext"));
      q.value.textContent = fmtLever(v) + " " + unitText(l.unit);
      q.reset.disabled = v === l.base;
      q.row.classList.toggle("changed", v !== l.base);
      q.status.textContent = v === l.base ? "Base value" : "Changed from base";
    }
    ui.reset.disabled = v === l.base;
    ui.row.classList.toggle("changed", v !== l.base);
    ui.outsideTag.hidden = !isOutside(l, v);
  }

  // ---------- recompute ----------
  function schedule() {
    if (pending) { return; }
    pending = true;
    requestAnimationFrame(function () { pending = false; render(); });
  }

  function presetByName(name) {
    for (var i = 0; i < D.presets.length; i++) { if (D.presets[i].name === name) { return D.presets[i]; } }
    return null;
  }
  function sameParams(a, b) {
    return D.levers.every(function (l) { return a[l.name] === b[l.name]; });
  }
  function metricDef(name) {
    for (var i = 0; i < D.metrics.length; i++) { if (D.metrics[i].name === name) { return D.metrics[i]; } }
    return null;
  }
  // display only: sentence case, keeping all-caps acronyms (ARR, CS) and numbers; model names are not changed
  function sentenceCase(s) {
    return s.split(" ").map(function (w, i) {
      if (/^[A-Z0-9]{2,}$/.test(w) || /\d/.test(w)) { return w; }
      return i === 0 ? w.charAt(0).toUpperCase() + w.slice(1).toLowerCase() : w.toLowerCase();
    }).join(" ");
  }
  function metricLabel(d) { return sentenceCase(metricLabelRaw(d)); }
  function metricLabelRaw(d) {
    var tu = TU.toLowerCase();
    switch (d.stat) {
      case "value_at": return d["var"] + " at " + tu + " " + d.time;
      case "time_of_max": return TU + " of peak " + d["var"];
      case "time_to_reach": return TU + " when " + d["var"] + " first reaches " + d.value;
      case "final": return d["var"] + " at the end";
      case "initial": return d["var"] + " at the start";
      default: return d.stat + " of " + d["var"];
    }
  }
  function metricUnit(d) { return /time/.test(d.stat) ? TU : VARS[d["var"]].unit; }
  function deltaText(v, b) {
    var delta = v - b;
    if (delta === 0 || (!isFinite(v) && v === b)) { return "Same as " + baselineLabel(); }
    if (!isFinite(delta)) { return baselineLabel() + " " + fmt(b); }
    var pct = b !== 0 ? " (" + (delta > 0 ? "+" : "−") + fmt(Math.abs(delta / b) * 100) + "%)" : "";
    return (delta > 0 ? "▲ +" : "▼ −") + fmt(Math.abs(delta)) + pct;
  }

  function renderBanner(outside) {
    var b = $("banner");
    b.hidden = !state.extend;
    if (!state.extend) { return; }
    b.textContent = "";
    b.insertAdjacentHTML("afterbegin", '<svg viewBox="0 0 20 20" aria-hidden="true" focusable="false"><path d="M10 2 19 18H1Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M10 8v4M10 14.5v.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>');
    b.appendChild(h("span", null, outside ?
      "Outside validated range: at least one lever is beyond the range the model was validated on. Every result on this page is labelled; none of them is validated." :
      "Extended ranges are on. No lever is outside its validated range yet; any result computed beyond it will be labelled \"outside validated range\"."));
  }

  function renderHeadline(vals, outside) {
    var root = $("headline");
    root.textContent = "";
    D.decision.headline.forEach(function (name) {
      var d = metricDef(name), isDecision = name === D.decision.metric;
      var tile = h("section", "tile" + (isDecision ? " decision" : ""));
      tile.setAttribute("aria-label", metricLabel(d));
      if (isDecision) { tile.appendChild(h("p", "tile-kicker", "Decision metric · " + (D.decision.maximize ? "higher is better" : "lower is better"))); }
      tile.appendChild(h("p", "tile-label", metricLabel(d)));
      var v = vals[name], b = baseMetrics[name];
      var val = h("p", "tile-value", fmt(v));
      val.appendChild(h("span", "tile-unit", unitText(metricUnit(d))));
      tile.appendChild(val);
      var dt = deltaText(v, b);
      tile.appendChild(h("p", "tile-delta", /^(Same as )?Baseline: /.test(dt) ? dt : dt + " vs " + baselineLabel() + ", " + fmt(b)));
      if (outside) { tile.appendChild(tagEl("outside validated range", "tag-outside")); }
      root.appendChild(tile);
    });
  }

  // ---------- presets ----------
  var presetButtons = [];
  function buildPresets() {
    var root = $("preset-list");
    D.presets.forEach(function (p) {
      var b = h("button", "btn preset", p.name);
      b.type = "button";
      b.setAttribute("aria-pressed", "false");
      b.addEventListener("click", function () {
        // a policy may sit outside a lever's validated range; without this the banner that explains the labels stays
        // hidden and the slider clamps to a value the run does not use (the Load handler below does the same)
        if (anyOutsideIn(p.params) && !state.extend) { $("extend").checked = true; state.extend = true; }
        D.levers.forEach(function (l) {
          state.params[l.name] = p.params[l.name];
          if (leverUI[l.name].notice) { leverUI[l.name].notice.textContent = ""; }
          syncLever(l);
        });
        schedule();
      });
      presetButtons.push({b: b, p: p});
      root.appendChild(b);
    });
  }
  function syncPresets() {
    presetButtons.forEach(function (x) { x.b.setAttribute("aria-pressed", String(sameParams(state.params, x.p.params))); });
  }

  // ---------- saved scenarios ----------
  var SLOTS = [
    {letter: "A", color: "var(--series-a)", dash: ""},
    {letter: "B", color: "var(--series-b)", dash: "8 3"},
    {letter: "C", color: "var(--series-c)", dash: "2 3"},
    {letter: "D", color: "var(--series-d)", dash: "10 3 2 3"}
  ];
  var saved = [];
  function changedSummary(params) {
    var ch = D.levers.filter(function (l) { return params[l.name] !== l.base; });
    if (!ch.length) { return "same as the base values"; }
    var txt = ch.slice(0, 2).map(function (l) { return l.name + " " + fmtLever(params[l.name]); }).join("; ");
    return txt + (ch.length > 2 ? "; +" + (ch.length - 2) + " more" : "");
  }
  function saveScenario() {
    if (saved.length >= SLOTS.length) { return; }
    var used = saved.map(function (x) { return x.slot.letter; });
    var slot = SLOTS.filter(function (x) { return used.indexOf(x.letter) < 0; })[0];
    var params = Object.assign({}, state.params);
    var run = SDEngine.run(params);
    saved.push({slot: slot, params: params, run: run, metrics: SDMetrics.all(run, D.metrics), outside: anyOutsideIn(params)});
    saved.sort(function (a, b) { return a.slot.letter < b.slot.letter ? -1 : 1; });
    renderSaved();
    $("comparison-details").open = true;
    schedule();
  }
  function anyOutsideIn(params) { return D.levers.some(function (l) { return isOutside(l, params[l.name]); }); }
  function renderSaved() {
    var ul = $("saved");
    ul.textContent = "";
    saved.forEach(function (sc) {
      var li = h("li", "saved-item");
      var keyBox = h("span", "saved-key");
      keyBox.innerHTML = '<svg viewBox="0 0 22 12" aria-hidden="true" focusable="false"><line x1="1" y1="6" x2="21" y2="6" stroke-width="2.5"/></svg>';
      var line = keyBox.querySelector("line");
      line.setAttribute("stroke", sc.slot.color);
      line.setAttribute("stroke-dasharray", sc.slot.dash);
      li.appendChild(keyBox);
      li.appendChild(h("strong", null, sc.slot.letter));
      var desc = h("span", "saved-desc", changedSummary(sc.params));
      li.appendChild(desc);
      if (sc.outside) { li.appendChild(tagEl("outside validated range", "tag-outside")); }
      var load = h("button", "btn btn-quiet", "Load");
      load.type = "button";
      load.setAttribute("aria-label", "Load scenario " + sc.slot.letter + " into the levers");
      load.addEventListener("click", function () {
        if (sc.outside && !state.extend) { $("extend").checked = true; state.extend = true; }
        D.levers.forEach(function (l) { state.params[l.name] = sc.params[l.name]; syncLever(l); });
        schedule();
      });
      var rm = h("button", "btn btn-quiet remove", "Remove");
      rm.type = "button";
      rm.setAttribute("aria-label", "Remove scenario " + sc.slot.letter);
      rm.addEventListener("click", function () {
        saved = saved.filter(function (x) { return x !== sc; });
        renderSaved();
        schedule();
      });
      li.appendChild(load);
      li.appendChild(rm);
      ul.appendChild(li);
    });
    var btn = $("save-scenario");
    btn.disabled = saved.length >= SLOTS.length;
    btn.textContent = saved.length >= SLOTS.length ? "Four scenarios saved (remove one to save another)" : "Save current settings";
  }

  function renderCompare(vals, outside) {
    var tb = $("compare");
    tb.textContent = "";
    tb.appendChild(h("caption", "sr-only", "Every headline metric for the baseline (" + baseline.name + "), the current levers and each saved scenario"));
    var thead = h("thead"), tr = h("tr");
    ["Metric", baselineLabel(), "Current"].concat(saved.map(function (s) { return s.slot.letter; })).forEach(function (c, i) {
      var th = h("th", null, c);
      th.scope = "col";
      if (i === 0) { th.className = "left"; }
      tr.appendChild(th);
    });
    thead.appendChild(tr);
    tb.appendChild(thead);
    var body = h("tbody");
    D.metrics.forEach(function (d) {
      var r = h("tr"), b = baseMetrics[d.name];
      var th = h("th", "left", metricLabel(d) + " (" + unitText(metricUnit(d)) + ")");
      th.scope = "row";
      if (d.name === D.decision.metric) { th.appendChild(h("span", "decision-mark", " · decision metric")); }
      r.appendChild(th);
      r.appendChild(h("td", null, fmt(b)));
      function cell(v, out) {
        var td = h("td");
        td.appendChild(h("span", "cmp-val", fmt(v)));
        var dt = deltaText(v, b);
        if (!/^Same as /.test(dt)) { td.appendChild(h("span", "cmp-delta", dt)); }
        if (out) { td.appendChild(h("span", "cmp-delta", "outside validated range")); }
        return td;
      }
      r.appendChild(cell(vals[d.name], outside));
      saved.forEach(function (sc) { r.appendChild(cell(sc.metrics[d.name], sc.outside)); });
      body.appendChild(r);
    });
    tb.appendChild(body);
  }

  // ---------- charts ----------
  // The Monte Carlo band follows the line it belongs to: if the current levers equal a preset that has a band for this
  // variable, that band is the current setting's; otherwise the band of the baseline's preset is shown, labelled as the
  // baseline's (the current single run has no band).
  function bandSetFor(v, params) {
    for (var i = 0; i < D.bands.length; i++) {
      var b = D.bands[i], p = presetByName(b.preset);
      if (b.series[v] && p && sameParams(params, p.params)) { return b; }
    }
    return null;
  }
  function bandsFor(v, compact) {
    var cur = bandSetFor(v, state.params), base = bandSetFor(v, baseline.params), b = cur || base;
    if (!b) { return {bands: [], note: ""}; }
    var s = b.series[v], pre = cur ? "" : "Baseline band ";
    var note = cur ?
      (compact ? "Band: current levers (preset \"" + b.preset + "\"), Monte Carlo P5–P95 and P25–P75." :
        b.label + ". Band of the current levers (preset \"" + b.preset + "\"); from " + b.source + ".") :
      (compact ? "Baseline band (grey, hatched): preset \"" + b.preset + "\"; the current single run has no band." :
        "Baseline band (grey, hatched): " + b.label + " for the baseline (" + baseline.name + ", preset \"" + b.preset +
        "\"). It is not the uncertainty of the current line; the current single run has no band. From " + b.source + ".");
    return {
      bands: [
        {label: pre + "P5–P95", short: pre + "P5–P95", time: b.time, lo: s.P5, hi: s.P95, hatch: !cur,
          fill: cur ? "var(--band-outer)" : "var(--band-base-outer)"},
        {label: pre + "P25–P75", short: pre + "P25–P75", time: b.time, lo: s.P25, hi: s.P75, hatch: !cur,
          fill: cur ? "var(--band-inner)" : "var(--band-base-inner)"}
      ],
      note: note
    };
  }
  function seriesFor(v, run) {
    var out = [{label: baselineLabel(), values: baseRun.series[v], color: "var(--series-baseline)", dash: "6 4"}];
    saved.forEach(function (sc) {
      out.push({label: "Scenario " + sc.slot.letter, values: sc.run.series[v], color: sc.slot.color, dash: sc.slot.dash,
        endLabel: sc.slot.letter});
    });
    out.push({label: "Current levers (single run)", values: run.series[v], color: "var(--series-current)", width: 2.5});
    return out;
  }
  function about(name) { return function () { return infoCard(name); }; }

  var chartObjs = [], group = new SDCharts.Group(), gridLegends = [];
  function buildCharts() {
    var root = $("charts"), k = 0;
    D.charts.forEach(function (c) {
      if (c.kind === "grid") {
        var sec = h("details", "card grid-card");
        sec.open = (D.intake && D.intake.audience === "modellers") || c.open !== false;
        var hd = h("summary", "card-head"), hg = h("div"), h2 = h("h2", null, c.title);
        h2.id = "grid-" + c.id.replace(/[^a-z0-9]+/gi, "-");
        hg.appendChild(h2);
        hg.appendChild(h("p", "card-sub", c.vars.length + (c.vars.length === 1 ? " chart" : " charts") +
          " · each with its own unit and axis · single runs"));
        hd.appendChild(hg);
        sec.appendChild(hd);
        var lg = h("ul", "legend");
        lg.setAttribute("aria-label", "Legend for " + c.title);
        sec.appendChild(lg);
        gridLegends.push(lg);
        var grid = h("div", "mini-grid");
        sec.appendChild(grid);
        root.appendChild(sec);
        c.vars.forEach(function (v) {
          var card = h("div", "mini");
          card.id = "chart-" + k;
          grid.appendChild(card);
          var ch = new SDCharts.LineChart(card, {id: "chart-" + k + "-c", title: v, compact: true, about: about(v)});
          ch.v = v;
          group.add(ch);
          chartObjs.push(ch);
          k++;
        });
      } else {
        var card = h("section", "card");
        card.id = "chart-" + k;
        root.appendChild(card);
        var ch = new SDCharts.LineChart(card, {id: "chart-" + k + "-c", title: c.title, about: about(c.vars[0])});
        ch.v = c.vars[0];
        ch.mainTitle = c.title;
        group.add(ch);
        chartObjs.push(ch);
        k++;
      }
    });
  }
  function renderCharts(run, outside) {
    var legendSeries = null;
    chartObjs.forEach(function (ch) {
      var v = ch.v, unit = unitText(VARS[v].unit), b = bandsFor(v, ch.compact), series = seriesFor(v, run);
      legendSeries = legendSeries || series;
      ch.update({
        id: ch.opts.id, title: ch.mainTitle || v, timeUnit: TU, time: run.time, fmt: fmt, fmtAxis: fmtAxis,
        compact: ch.compact, about: ch.opts.about,
        subtitle: unit + (ch.compact ? "" : " · single run at the current levers vs " + baselineLabel()) +
          (outside ? " · outside validated range" : ""),
        series: series, bands: b.bands, bandNote: b.note
      });
    });
    gridLegends.forEach(function (lg) { SDCharts.legend(lg, legendSeries || [], []); });
  }

  var resultsStale = false;
  function render() {
    var run = SDEngine.run(state.params), outside = anyOutside(), vals = SDMetrics.all(run, D.metrics);
    lastRun = run;
    if (structure) {
      var rp = pendingRipple ? leverNode(pendingRipple) : null;
      pendingRipple = null;
      structure.setRuns(run, baseRun, rp);
      if (!$("structure").hidden) { structure.render(); }
    }
    renderBanner(outside);
    // the Results view is redrawn only while it is shown; switching back to it redraws it from the current run
    resultsStale = $("results").hidden;
    if (!resultsStale) {
      renderHeadline(vals, outside);
      renderCompare(vals, outside);
      renderCharts(run, outside);
    }
    syncPresets();
    $("reset-all").disabled = D.levers.every(function (l) { return state.params[l.name] === l.base; });
  }

  // ---------- static parts ----------
  function runLabel() {
    var p = $("runlabel");
    p.appendChild(h("strong", null, "Single run, not a forecast. "));
    p.appendChild(document.createTextNode("Each change re-runs the validated model once at the current lever settings. " +
      "Uncertainty is shown only by the Monte Carlo band, where it applies. "));
    var a = h("button", "btn btn-quiet", "Read the model limits");
    a.type = "button";
    a.addEventListener("click", openLimits);
    p.appendChild(a);
  }

  function provenance() {
    var P = D.provenance, f = $("provenance");
    f.appendChild(h("p", null, "Engine generated from " + P.model_file + " (PySD " + P.pysd + " translation); " +
      "parity with PySD checked on " + P.parity_runs + " runs (" + P.parity_random + " random lever settings inside the validated ranges, corners, presets), " +
      P.parity_series + " series: largest scale-relative difference " + P.parity_max_scale_rel.toExponential(1) +
      ", largest pointwise relative difference " + P.parity_max_pointwise_rel.toExponential(1) +
      ", headline metrics " + P.headline_max_rel.toExponential(1) + " (tolerance " + P.tolerance + ")."));
    f.appendChild(h("p", null, "Validation: " + P.validation + ". Parameter sources and confidence tags: assumptions_register.md."));
    var code = h("p");
    code.appendChild(document.createTextNode("Model sha256 "));
    code.appendChild(h("code", null, P.model_sha256));
    f.appendChild(code);
    // release stamp: the files this page was released from (the build refuses unless they pass)
    if (D.release) {
      var rel = h("details", "release");
      rel.appendChild(h("summary", null, "Released from: " + D.release.gate));
      var ul = h("ul");
      Object.keys(D.release.files).sort().forEach(function (k) {
        var li = h("li");
        li.appendChild(document.createTextNode(k + " sha256 "));
        li.appendChild(h("code", null, D.release.files[k]));
        ul.appendChild(li);
      });
      rel.appendChild(ul);
      f.appendChild(rel);
    }
  }

  // ---------- model limits (verbatim markdown, rendered without HTML injection) ----------
  function inline(parent, text) {
    var re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g, last = 0, m;
    while ((m = re.exec(text))) {
      if (m.index > last) { parent.appendChild(document.createTextNode(text.slice(last, m.index))); }
      var t = m[0];
      if (t.slice(0, 2) === "**") { parent.appendChild(h("strong", null, t.slice(2, -2))); }
      else if (t[0] === "`") { parent.appendChild(h("code", null, t.slice(1, -1))); }
      else { parent.appendChild(h("em", null, t.slice(1, -1))); }
      last = m.index + t.length;
    }
    if (last < text.length) { parent.appendChild(document.createTextNode(text.slice(last))); }
  }
  function renderMarkdown(root, md) {
    var lines = md.split("\n"), i = 0;
    function cells(l) { return l.trim().replace(/^\||\|$/g, "").split("|").map(function (c) { return c.trim(); }); }
    while (i < lines.length) {
      var l = lines[i];
      if (!l.trim()) { i++; continue; }
      var hm = /^(#+)\s*(.*)$/.exec(l);
      if (hm) { var hh = h(hm[1].length <= 2 ? "h2" : "h3"); inline(hh, hm[2]); root.appendChild(hh); i++; continue; }
      if (/^\s*\|/.test(l) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
        var tb = h("table"), tr = h("tr");
        cells(l).forEach(function (c) { var th = h("th"); inline(th, c); tr.appendChild(th); });
        var thead = h("thead"); thead.appendChild(tr); tb.appendChild(thead);
        var body = h("tbody");
        i += 2;
        while (i < lines.length && /^\s*\|/.test(lines[i])) {
          var r = h("tr");
          cells(lines[i]).forEach(function (c) { var td = h("td"); inline(td, c); r.appendChild(td); });
          body.appendChild(r);
          i++;
        }
        tb.appendChild(body);
        root.appendChild(tb);
        continue;
      }
      if (/^\s*[-*]\s+/.test(l)) {
        var ul = h("ul");
        while (i < lines.length && lines[i].trim() && !/^#/.test(lines[i]) && !/^\s*\|/.test(lines[i])) {
          if (/^\s*[-*]\s+/.test(lines[i])) { var li = h("li"); inline(li, lines[i].replace(/^\s*[-*]\s+/, "")); ul.appendChild(li); }
          else { ul.lastChild.appendChild(document.createTextNode(" ")); inline(ul.lastChild, lines[i].trim()); }
          i++;
        }
        root.appendChild(ul);
        continue;
      }
      var para = [];
      while (i < lines.length && lines[i].trim() && !/^#/.test(lines[i]) && !/^\s*[-*]\s+/.test(lines[i]) && !/^\s*\|/.test(lines[i])) {
        para.push(lines[i].trim());
        i++;
      }
      var p = h("p"); inline(p, para.join(" ")); root.appendChild(p);
    }
  }
  function openLimits() {
    var dlg = $("limits-dialog");
    if (typeof dlg.showModal === "function") { dlg.showModal(); } else { dlg.setAttribute("open", ""); }
    $("limits-close").focus();
  }

  // ---------- theme ----------
  var THEMES = ["system", "light", "dark"];
  function applyTheme(t) {
    if (t === "system") { document.documentElement.removeAttribute("data-theme"); }
    else { document.documentElement.setAttribute("data-theme", t); }
    var btn = $("btn-theme"), next = THEMES[(THEMES.indexOf(t) + 1) % 3];
    btn.textContent = "Theme: " + t;
    btn.setAttribute("aria-label", "Colour theme: " + t + ". Activate to switch to " + next + ".");
    try { localStorage.setItem("sd-explorer-theme", t); } catch (e) { /* storage unavailable: theme not remembered */ }
  }
  function initTheme() {
    var t = "system";
    try { t = localStorage.getItem("sd-explorer-theme") || "system"; } catch (e) { t = "system"; }
    if (THEMES.indexOf(t) < 0) { t = "system"; }
    applyTheme(t);
    $("btn-theme").addEventListener("click", function () {
      var cur = document.documentElement.getAttribute("data-theme") || "system";
      applyTheme(THEMES[(THEMES.indexOf(cur) + 1) % 3]);
    });
  }

  // ---------- views: Results / Structure (desktop), Levers / Results / Structure (mobile tabs) ----------
  var structure = null, lastRun = null;
  // the Structure tab shows the time picked on its scrubber; the default is the decision metric's time
  function defaultTime(run) {
    var d = metricDef(D.decision.metric), i = d && d.stat === "value_at" ? run.time.indexOf(d.time) : -1;
    return i >= 0 ? i : run.time.length - 1;
  }
  function openStructure() {
    if (!structure) {
      structure = new SDStructure.Structure($("structure"), D, {infoCard: infoCard, defaultTime: defaultTime,
        baselineLabel: baselineLabel, onTime: function (i) { group.show(null, i); },
        runDt: function () { return SDEngine.run(state.params, {saveper: D.ltm.dt}); }});
      group.onShow = function (i) { structure.setTime(i, "chart"); };
    }
    structure.setRuns(lastRun || SDEngine.run(state.params), baseRun, null);
    structure.fit();
    // audience chosen at intake: modellers see every variable, a workshop sees the flow values
    if (!structure.audienceApplied && D.intake) {
      structure.audienceApplied = true;
      var box = D.intake.audience === "modellers" ? $("show-all") : D.intake.audience === "workshop" ? $("st-values") : null;
      if (box && !box.checked) { box.checked = true; box.dispatchEvent(new Event("change")); }
    }
  }
  function initTabs() {
    var mq = window.matchMedia("(max-width: 760px)");
    var mobileTabs = [$("tab-levers"), $("tab-results"), $("tab-structure")];
    var viewTabs = [$("view-results"), $("view-structure")];
    var start = D.intake && D.intake.audience === "workshop" ? "structure" : "results";
    var cur = {mobile: start, view: start};
    function apply(focusTab) {
      var mobile = mq.matches, which = mobile ? cur.mobile : cur.view;
      $("levers").hidden = mobile && which !== "levers";
      $("results").hidden = which !== "results";
      $("structure").hidden = which !== "structure";
      mobileTabs.forEach(function (t) {
        var on = t.getAttribute("aria-controls") === which;
        t.setAttribute("aria-selected", String(on));
        t.tabIndex = on ? 0 : -1;
      });
      viewTabs.forEach(function (t) {
        var on = t.getAttribute("aria-controls") === cur.view;
        t.setAttribute("aria-selected", String(on));
        t.tabIndex = on ? 0 : -1;
      });
      if (which === "structure") { openStructure(); }
      if (which === "results" && resultsStale) { render(); }
      if (focusTab) { focusTab.focus(); }
    }
    function select(name, focus) {
      cur.mobile = name;
      if (name !== "levers") { cur.view = name; }
      apply(focus);
    }
    [mobileTabs, viewTabs].forEach(function (group) {
      group.forEach(function (t, k) {
        t.addEventListener("click", function () { select(t.getAttribute("aria-controls")); });
        t.addEventListener("keydown", function (e) {
          var d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
          if (!d) { return; }
          e.preventDefault();
          var nt = group[(k + d + group.length) % group.length];
          select(nt.getAttribute("aria-controls"), nt);
        });
      });
    });
    mq.addEventListener("change", function () { apply(); });
    apply();
  }

  // Print reveals existing explanatory content, then restores the reader's disclosures.
  var printDisclosureState = null, printView = null;
  window.addEventListener("beforeprint", function () {
    if (printDisclosureState) { return; }
    printView = structure ? {view: Object.assign({}, structure.view), layout: structure.layout} : null;
    // Results can be stale while Structure is active. Reuse the normal renderer with current inputs.
    var resultsHidden = $("results").hidden;
    $("results").hidden = false;
    render();
    if (!structure) { openStructure(); }
    printDisclosureState = Array.prototype.map.call(document.querySelectorAll("details"), function (d) {
      var item = {element: d, open: d.open}; d.open = true; return item;
    });
    // Printing must not wait for asynchronous disclosure/resize events to refresh hidden charts.
    chartObjs.forEach(function (chart) { chart.draw(); chart.renderTable(); });
    $("results").hidden = resultsHidden;
  });
  window.addEventListener("afterprint", function () {
    (printDisclosureState || []).forEach(function (item) { item.element.open = item.open; });
    printDisclosureState = null;
    if (printView) {
      structure.view = printView.view;
      structure.layout = printView.layout;
      structure.render();
      printView = null;
    }
  });

  // ---------- init ----------
  window.SDFormat = {fmt: fmt, unitText: unitText};
  // read-only view of the page state (used by the browser tests; changes nothing)
  window.SDExplorer = {
    params: function () { return Object.assign({}, state.params); },
    baselineParams: function () { return Object.assign({}, baseline.params); }
  };
  (function initBaseline() {
    var sel = $("baseline-select");
    BASELINES.forEach(function (b, i) {
      var o = h("option", null, b.name);
      o.value = String(i);
      o.setAttribute("data-params", JSON.stringify(b.params));
      if (b === baseline) { o.selected = true; }    // the dropdown shows the baseline the page computes against
      sel.appendChild(o);
    });
    sel.addEventListener("change", function () {
      baseline = BASELINES[Number(sel.value)];
      baseRun = SDEngine.run(baseline.params);
      baseMetrics = SDMetrics.all(baseRun, D.metrics);
      schedule();
    });
  })();
  $("page-title").textContent = D.title.charAt(0).toUpperCase() + D.title.slice(1);
  $("toggle-metrics").addEventListener("click", function () {
    var expanded = $("toggle-metrics").getAttribute("aria-expanded") !== "true";
    $("toggle-metrics").setAttribute("aria-expanded", String(expanded));
    $("headline").classList.toggle("show-secondary", expanded);
    $("toggle-metrics").textContent = expanded ? "Fewer headline metrics" : "More headline metrics";
  });
  $("trust-link").addEventListener("click", function () {
    var release = $("provenance").querySelector("details");
    if (release) { release.open = true; release.querySelector("summary").focus(); }
  });
  buildLevers();
  buildPresets();
  buildQuickControls();
  buildCharts();
  D.levers.forEach(syncLever);
  $("save-scenario").addEventListener("click", saveScenario);
  renderSaved();
  $("extend").addEventListener("change", function () {
    state.extend = $("extend").checked;
    D.levers.forEach(function (l) {
      if (!state.extend) {
        var v = state.params[l.name], c = Math.min(l.high, Math.max(l.low, v));
        if (c !== v && !l.fixed && l.exposed !== false) { state.params[l.name] = c; leverUI[l.name].notice.textContent = "Returned to the validated range: " + fmtLever(c) + "."; }
      }
      syncLever(l);
    });
    schedule();
  });
  $("reset-all").addEventListener("click", function () {
    D.levers.forEach(function (l) { state.params[l.name] = l.base; if (leverUI[l.name].notice) { leverUI[l.name].notice.textContent = ""; } syncLever(l); });
    schedule();
  });
  $("btn-limits").addEventListener("click", openLimits);
  $("limits-close").addEventListener("click", function () { $("limits-dialog").close(); });
  renderMarkdown($("limits-body"), D.model_limits);
  $("limits-src").textContent = D.model_limits;
  // page settings from the /sd-explorer intake: listed here so every assumed default is visible next to the limits
  if (D.intake) {
    var li = $("limits-intake");
    li.appendChild(h("h3", null, "Page settings assumed or chosen when this page was built"));
    li.appendChild(h("p", "muted", "These settings change only what the page shows first. They are not part of the validated " +
      "model and do not change its equations, parameters or ranges. " + (D.intake.mode === "asked" ? "Questions were asked; a " +
      "skipped question took its default." : D.intake.mode === "unattended" ? "Nobody could be asked (unattended run): every " +
      "setting is a default." : "No intake was recorded: every setting is a default.")));
    var ul = h("ul");
    ul.id = "intake-settings";
    D.intake.settings.forEach(function (x) {
      var item = h("li");
      item.setAttribute("data-source", x.source);
      item.appendChild(h("strong", null, x.setting + ": "));
      item.appendChild(document.createTextNode(x.value + " "));
      item.appendChild(h("em", null, "(" + x.source + ")"));
      ul.appendChild(item);
    });
    li.appendChild(ul);
  }
  runLabel();
  provenance();
  initTheme();
  initTabs();
  render();
})();
