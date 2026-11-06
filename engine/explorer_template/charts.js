// Line charts with bands, a crosshair synchronized across every chart (pointer and keyboard), legend, end labels
// and a data table. Plain SVG, no library.
var SDCharts = (function () {
  "use strict";
  var NS = "http://www.w3.org/2000/svg"; // XML namespace identifier, not a network request

  function el(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    if (parent) { parent.appendChild(e); }
    return e;
  }
  function h(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text !== undefined) { e.textContent = text; }
    return e;
  }
  function niceStep(span, n) {
    var raw = span / Math.max(1, n), p = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / p;
    return (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * p;
  }
  function ticks(lo, hi, n) {
    if (!(hi > lo)) { hi = lo + (Math.abs(lo) || 1); }
    var s = niceStep(hi - lo, n), out = [];
    for (var v = Math.ceil(lo / s - 1e-9) * s; v <= hi + s * 1e-9; v += s) { out.push(Math.abs(v) < s * 1e-9 ? 0 : v); }
    return out;
  }
  var uid = 0;
  // Hatched fill (baseline band shown while the levers differ): a grey wash crossed by 45-degree lines.
  function hatch(svg, base) {
    var id = "sd-hatch-" + (++uid), defs = el("defs", {}, svg);
    var p = el("pattern", {id: id, patternUnits: "userSpaceOnUse", width: 6, height: 6, patternTransform: "rotate(45)"}, defs);
    el("rect", {x: 0, y: 0, width: 6, height: 6, fill: base}, p);
    el("line", {x1: 0, y1: 0, x2: 0, y2: 6, stroke: "var(--band-hatch)", "stroke-width": 1.5}, p);
    return "url(#" + id + ")";
  }
  function key(parent, color, dash, band, hatched) {
    var s = el("svg", {viewBox: "0 0 22 12", "aria-hidden": "true", focusable: "false"}, parent);
    if (band) {
      el("rect", {x: 0, y: 1, width: 22, height: 10, rx: 2, fill: hatched ? hatch(s, color) : color}, s);
    } else {
      el("line", {x1: 1, y1: 6, x2: 21, y2: 6, stroke: color, "stroke-width": 2.5, "stroke-dasharray": dash || "",
        "stroke-linecap": "butt"}, s);
    }
    return s;
  }
  function legend(ul, series, bands) {
    ul.textContent = "";
    (bands || []).forEach(function (b) {
      var li = h("li");
      key(li, b.fill, "", true, b.hatch);
      li.appendChild(document.createTextNode(b.label));
      ul.appendChild(li);
    });
    series.forEach(function (s) {
      var li = h("li");
      key(li, s.color, s.dash);
      li.appendChild(document.createTextNode(s.label));
      ul.appendChild(li);
    });
  }

  // ---------- synchronized crosshair ----------
  function Group() { this.charts = []; }
  Group.prototype.add = function (c) { this.charts.push(c); c.group = this; };
  Group.prototype.show = function (src, i) {
    this.charts.forEach(function (c) { c.showCross(i, c === src); });
    if (src && this.onShow) { this.onShow(i); }   // a reader moved the crosshair: tell the Structure tab's scrubber
  };
  Group.prototype.hide = function () { this.charts.forEach(function (c) { c.hideCross(); }); };

  function LineChart(root, opts) {
    var self = this;
    this.root = root;
    this.opts = opts;
    this.idx = null;
    this.compact = !!opts.compact;
    root.textContent = "";
    var head = h("div", "card-head");
    var hgroup = h("div");
    this.titleEl = h(this.compact ? "h3" : "h2", null, opts.title);
    this.titleEl.id = opts.id + "-title";
    this.subEl = h("p", "card-sub");
    hgroup.appendChild(this.titleEl);
    hgroup.appendChild(this.subEl);
    head.appendChild(hgroup);
    if (opts.about) {
      var btn = h("button", "btn btn-quiet about-btn", "About");
      btn.type = "button";
      btn.setAttribute("aria-label", "About " + opts.title);
      btn.setAttribute("aria-expanded", "false");
      head.appendChild(btn);
      this.aboutCard = opts.about();
      this.aboutCard.hidden = true;
      this.aboutCard.id = opts.id + "-about";
      btn.setAttribute("aria-controls", this.aboutCard.id);
      btn.addEventListener("click", function () {
        self.aboutCard.hidden = !self.aboutCard.hidden;
        btn.setAttribute("aria-expanded", String(!self.aboutCard.hidden));
      });
    }
    root.appendChild(head);
    if (this.aboutCard) { root.appendChild(this.aboutCard); }
    if (!this.compact) {
      this.legend = h("ul", "legend");
      this.legend.setAttribute("aria-label", "Legend");
      root.appendChild(this.legend);
    }
    this.box = h("div", "chart");
    this.box.tabIndex = 0;
    this.box.setAttribute("role", "group");
    this.box.setAttribute("aria-labelledby", this.titleEl.id);
    this.box.setAttribute("aria-describedby", "sd-chart-help");
    root.appendChild(this.box);
    this.status = h("p", "chart-status", "Preparing chart…");
    this.status.setAttribute("role", "status");
    this.box.appendChild(this.status);
    this.svg = el("svg", {"class": "plot", "aria-hidden": "true"}, this.box);
    this.tip = h("div", "tooltip");
    this.tip.hidden = true;
    this.box.appendChild(this.tip);
    this.bandNote = h("p", "band-note");
    root.appendChild(this.bandNote);
    this.table = h("details", "table-view");
    this.table.appendChild(h("summary", null, "Data table"));
    this.tableWrap = h("div", "table-wrap");
    this.table.appendChild(this.tableWrap);
    this.table.addEventListener("toggle", this.renderTable.bind(this));
    root.appendChild(this.table);
    this.box.addEventListener("pointermove", function (e) { self.pointer(e); });
    this.box.addEventListener("pointerleave", function () { self.hideAll(); });
    this.box.addEventListener("keydown", function (e) { self.key(e); });
    this.box.addEventListener("blur", function () { self.hideAll(); });
    var disclosure = root.closest("details");
    if (disclosure) {
      disclosure.addEventListener("toggle", function () { if (disclosure.open) { self.draw(); } });
    }
    if (typeof ResizeObserver !== "undefined") {
      new ResizeObserver(function () { self.draw(); }).observe(this.box);
    }
  }

  LineChart.prototype.update = function (opts) {
    this.opts = opts;
    this.titleEl.textContent = opts.title;
    this.subEl.textContent = opts.subtitle || "";
    this.bandNote.textContent = opts.bandNote || "";
    this.bandNote.hidden = !opts.bandNote;
    if (this.legend) { legend(this.legend, opts.series, opts.bands); }
    this.draw();
    if (this.table.open) { this.renderTable(); }
  };

  LineChart.prototype.draw = function () {
    var o = this.opts, svg = this.svg;
    if (!o || !o.series) { return; }
    var available = o.time && o.time.length && o.series.some(function (series) {
      return series.values.some(function (v) { return typeof v === "number" && isFinite(v); });
    });
    this.status.hidden = !!available;
    if (!available) {
      this.status.textContent = "No finite data to display for this run. Review the model limits and current settings.";
      svg.textContent = ""; this.tip.hidden = true; return;
    }
    // Keep updated series in opts, but avoid repainting an already-built closed disclosure.
    // ResizeObserver redraws it when the group is opened; the first draw still creates all accessible chart parts.
    if (this.cross && (this.box.closest("details:not([open])") || !this.box.getClientRects().length)) { return; }
    var W = Math.max(240, this.box.clientWidth || 600);
    var H = this.compact ? (W < 420 ? 170 : 190) : (W < 520 ? 220 : 300);
    var ends = o.series.some(function (s) { return s.endLabel; });
    var m = {l: 54, r: ends ? 24 : 12, t: 10, b: this.compact ? 34 : 44};
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.textContent = "";
    var t = o.time, n = t.length;
    var lo = Infinity, hi = -Infinity;
    function scan(a) { for (var i = 0; i < a.length; i++) { var v = a[i]; if (isFinite(v)) { if (v < lo) { lo = v; } if (v > hi) { hi = v; } } } }
    o.series.forEach(function (s) { scan(s.values); });
    (o.bands || []).forEach(function (b) { scan(b.lo); scan(b.hi); });
    if (!isFinite(lo)) { lo = 0; hi = 1; }
    if (lo > 0 && lo < hi * 0.35) { lo = 0; }
    var yt = ticks(lo, hi, this.compact ? 4 : 5);
    var y0 = Math.min(lo, yt[0]), y1 = Math.max(hi, yt[yt.length - 1]);
    var xt = ticks(t[0], t[n - 1], W < 520 ? 4 : 8);
    var X = function (v) { return m.l + (v - t[0]) / ((t[n - 1] - t[0]) || 1) * (W - m.l - m.r); };
    var Y = function (v) { return H - m.b - (v - y0) / ((y1 - y0) || 1) * (H - m.t - m.b); };
    this.X = X; this.Y = Y; this.W = W; this.H = H; this.m = m;
    var grid = el("g", {"class": "grid"}, svg);
    yt.forEach(function (v) {
      el("line", {x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v)}, grid);
      el("text", {x: m.l - 8, y: Y(v) + 4, "text-anchor": "end"}, svg).textContent = o.fmtAxis(v);
    });
    xt.forEach(function (v) {
      if (v < t[0] || v > t[n - 1]) { return; }
      // ticks() accumulates the step, so a fractional one leaves float noise (2020.1999999999998): round it off
      el("text", {x: X(v), y: H - m.b + 18, "text-anchor": "middle"}, svg).textContent = String(Number(v.toPrecision(12)));
    });
    el("line", {"class": "axis-line", x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b}, svg);
    if (!this.compact) {
      el("text", {x: (m.l + W - m.r) / 2, y: H - 4, "text-anchor": "middle"}, svg).textContent = o.timeUnit;
    }
    (o.bands || []).forEach(function (b) {
      var d = "";
      for (var i = 0; i < b.time.length; i++) { d += (i ? "L" : "M") + X(b.time[i]).toFixed(1) + "," + Y(b.hi[i]).toFixed(1); }
      for (var j = b.time.length - 1; j >= 0; j--) { d += "L" + X(b.time[j]).toFixed(1) + "," + Y(b.lo[j]).toFixed(1); }
      var attrs = {d: d + "Z", fill: b.hatch ? hatch(svg, b.fill) : b.fill, stroke: "none", "data-band": "1"};
      if (b.hatch) { attrs["data-hatched"] = "1"; }
      el("path", attrs, svg);
    });
    var labels = [];
    o.series.forEach(function (s) {
      var d = "", pen = false, last = -1;
      for (var i = 0; i < n; i++) {
        var v = s.values[i];
        if (!isFinite(v)) { pen = false; continue; }
        d += (pen ? "L" : "M") + X(t[i]).toFixed(1) + "," + Y(v).toFixed(1);
        pen = true;
        last = i;
      }
      el("path", {d: d, fill: "none", stroke: s.color, "stroke-width": s.width || 2, "stroke-dasharray": s.dash || "",
        "stroke-linejoin": "round", "stroke-linecap": s.dash ? "butt" : "round"}, svg);
      if (s.endLabel && last >= 0) { labels.push({text: s.endLabel, x: X(t[last]), y: Y(s.values[last])}); }
    });
    // end labels: placed top to bottom at least 12px apart; a label that would move more than 24px from its line is
    // dropped (the legend and the tooltip still name every line), so labels never stack into an unreadable block
    labels.sort(function (a, b) { return a.y - b.y; });
    var floor = -Infinity;
    labels.forEach(function (lb) {
      var y = Math.max(lb.y, floor + 12);
      if (y - lb.y > 24) { return; }
      floor = y;
      if (y !== lb.y) { el("line", {"class": "leader", x1: lb.x + 1, y1: lb.y, x2: lb.x + 4, y2: y - 1}, svg); }
      el("text", {"class": "end-label", x: lb.x + 5, y: y + 4}, svg).textContent = lb.text;
    });
    this.cross = el("g", {"class": "cross", visibility: "hidden"}, svg);
    el("line", {"class": "crosshair", x1: 0, x2: 0, y1: m.t, y2: H - m.b}, this.cross);
    this.dots = o.series.map(function (s) {
      return el("circle", {r: 4, fill: s.color, stroke: "var(--surface)", "stroke-width": 2}, this.cross);
    }, this);
    if (this.idx !== null) { this.showCross(this.idx, !this.tip.hidden); }
  };

  LineChart.prototype.nearest = function (px) {
    var t = this.opts.time, best = 0, bd = Infinity;
    for (var i = 0; i < t.length; i++) { var d = Math.abs(this.X(t[i]) - px); if (d < bd) { bd = d; best = i; } }
    return best;
  };
  LineChart.prototype.pointer = function (e) {
    var r = this.svg.getBoundingClientRect();
    if (!r.width) { return; }
    this.showAll(this.nearest((e.clientX - r.left) * this.W / r.width));
  };
  LineChart.prototype.key = function (e) {
    var n = this.opts.time.length, i = this.idx === null ? 0 : this.idx;
    if (e.key === "ArrowRight") { i = Math.min(n - 1, i + 1); }
    else if (e.key === "ArrowLeft") { i = Math.max(0, i - 1); }
    else if (e.key === "Home") { i = 0; }
    else if (e.key === "End") { i = n - 1; }
    else if (e.key === "Escape") { this.hideAll(); return; }
    else { return; }
    e.preventDefault();
    this.showAll(i);
  };
  LineChart.prototype.showAll = function (i) {
    if (this.group) { this.group.show(this, i); } else { this.showCross(i, true); }
  };
  LineChart.prototype.hideAll = function () {
    if (this.group) { this.group.hide(); } else { this.hideCross(); }
  };
  LineChart.prototype.hideCross = function () {
    this.idx = null;
    this.tip.hidden = true;
    if (this.cross) { this.cross.setAttribute("visibility", "hidden"); }
  };
  LineChart.prototype.showCross = function (i, withTip) {
    var o = this.opts;
    if (!this.cross || i >= o.time.length) { return; }
    this.idx = i;
    // a chart that was updated while collapsed or hidden keeps the dots of its last drawing: draw() shows the crosshair at this.idx once it is redrawn
    if (this.dots.length !== o.series.length) { return; }
    var x = this.X(o.time[i]), Y = this.Y;
    this.cross.setAttribute("visibility", "visible");
    this.cross.firstChild.setAttribute("x1", x);
    this.cross.firstChild.setAttribute("x2", x);
    o.series.forEach(function (s, k) {
      var v = s.values[i], c = this.dots[k];
      c.setAttribute("visibility", isFinite(v) ? "visible" : "hidden");
      if (isFinite(v)) { c.setAttribute("cx", x); c.setAttribute("cy", Y(v)); }
    }, this);
    var tip = this.tip;
    if (!withTip) { tip.hidden = true; return; }
    tip.textContent = "";
    tip.appendChild(h("div", "tt-time", o.timeUnit + " " + o.time[i]));
    o.series.slice().reverse().forEach(function (s) {
      var row = h("div", "tt-row");
      key(row, s.color, s.dash);
      row.appendChild(h("span", "tt-val", o.fmt(s.values[i])));
      row.appendChild(h("span", "tt-name", s.label));
      tip.appendChild(row);
    });
    (o.bands || []).forEach(function (b) {
      var j = b.time.indexOf(o.time[i]);
      if (j < 0) { return; }
      var row = h("div", "tt-row");
      key(row, b.fill, "", true, b.hatch);
      row.appendChild(h("span", "tt-val", o.fmt(b.lo[j]) + " – " + o.fmt(b.hi[j])));
      row.appendChild(h("span", "tt-name", b.short));
      tip.appendChild(row);
    });
    tip.hidden = false;
    var bw = this.box.clientWidth, px = x / this.W * bw;
    var left = px + 14;
    if (left + tip.offsetWidth > bw) { left = Math.max(0, px - 14 - tip.offsetWidth); }
    tip.style.left = left + "px";
    tip.style.top = "8px";
  };

  LineChart.prototype.renderTable = function () {
    if (!this.table.open) { return; }
    var o = this.opts, wrap = this.tableWrap;
    wrap.textContent = "";
    var tb = h("table", "data"), thead = h("thead"), tr = h("tr");
    tb.appendChild(h("caption", "sr-only", o.title));
    tr.appendChild(h("th", null, o.timeUnit));
    o.series.forEach(function (s) { tr.appendChild(h("th", null, s.label)); });
    (o.bands || []).forEach(function (b) { tr.appendChild(h("th", null, b.short + " low")); tr.appendChild(h("th", null, b.short + " high")); });
    thead.appendChild(tr);
    tb.appendChild(thead);
    var body = h("tbody");
    o.time.forEach(function (tv, i) {
      var r = h("tr");
      r.appendChild(h("td", null, String(tv)));
      o.series.forEach(function (s) { r.appendChild(h("td", null, o.fmt(s.values[i]))); });
      (o.bands || []).forEach(function (b) {
        var j = b.time.indexOf(tv);
        r.appendChild(h("td", null, j < 0 ? "" : o.fmt(b.lo[j])));
        r.appendChild(h("td", null, j < 0 ? "" : o.fmt(b.hi[j])));
      });
      body.appendChild(r);
    });
    tb.appendChild(body);
    wrap.appendChild(tb);
  };

  return {LineChart: LineChart, Group: Group, legend: legend};
})();
