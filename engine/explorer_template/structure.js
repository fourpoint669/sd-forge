// Structure tab: stock-and-flow and causal-loop views of the whole model, drawn from the build's structure data
// (engine/explorer_structure.py). Semantic zoom, sector collapse, minimap, search, focus mode and loop isolation.
// Every encoding is explained in the legend; link polarity is carried by glyph and line style, never colour alone.
// Pooling flags, shared by the panel and the tests: for each capacity-capped drain (stock S, time constant T,
// capacity C, from the delay audit): demand = S / T; ratio = demand / C; binding(t) = ratio >= bind;
// build_up(t) = t >= window and (S(t) - S(t - window)) / max(|S(t - window)|, 1e-12) >= build; flagged = both;
// binding_only = binding and not build_up: the limit is active but the stock has not (yet) built up past the threshold.
var SDPooling = (function () {
  "use strict";
  var capped = [];
  function init(structure) { capped = structure.pooling.capped; }
  function defaults() { return {bind: 1, build: 0.05, window: 6}; }
  function compute(run, base, th) {
    var t = run.time, w = Math.round(th.window / (t[1] - t[0]));
    return capped.map(function (c) {
      var S = run.series[c.stock_name], T = run.series[c.tau_name], C = run.series[c.cap_name];
      var out = {stock: c.stock_name, cap: c.cap_name, ratio: [], demand: [], capacity: [], binding: [], build_up: [], flagged: [], growth: [],
        from: [], to: [], binding_only: [], time_index: []};
      for (var i = 0; i < S.length; i++) {
        var demand = S[i] / T[i], ratio = demand / C[i];
        var g = i >= w ? (S[i] - S[i - w]) / Math.max(Math.abs(S[i - w]), 1e-12) : NaN;
        out.demand.push(demand); out.capacity.push(C[i]); out.ratio.push(ratio); out.growth.push(g);
        out.from.push(i >= w ? S[i - w] : NaN); out.to.push(S[i]);
        out.binding.push(ratio >= th.bind);
        out.build_up.push(i >= w && g >= th.build);
        out.flagged.push(out.binding[i] && out.build_up[i]);
        out.binding_only.push(out.binding[i] && !out.build_up[i]);
        out.time_index.push(i);
      }
      return out;
    });
  }
  return {init: init, defaults: defaults, compute: compute};
})();

var SDStructure = (function () {
  "use strict";
  var NS = "http://www.w3.org/2000/svg"; // XML namespace identifier, not a network request
  var DASH = {"+": null, "-": "7 4", "+/-": "9 3 2 3", "0": "1 4"};
  var GLYPH = {"+": "+", "-": "−", "+/-": "±", "0": "0"};
  var SIGN_WORD = {"+": "positive", "-": "negative", "+/-": "changes sign during the run", "0": "inactive at base settings"};
  var METHOD = {
    ltm: "sign from the loops-that-matter link score in the base run",
    loop_check: "sign from the link score in the run with the [loop_check] settings of validation.toml",
    perturbation: "sign from a small change of the cause in the equation, evaluated over the base run",
    perturbation_optional_on: "sign from a small change of the cause, evaluated with the optional effects at their validated high values",
    inactive: "no effect at the base settings (a switch threshold or a floor that does not bind)"
  };
  var SEMANTIC_K = 0.8;      // screen pixels per diagram unit above which auxiliaries and inputs appear
  var DETAIL_OUT_K = 0.6;    // in the detail layout, below this scale the view returns to the overview (hysteresis)
  var FLOW_LABEL_K = 0.55;
  var PIPE_LANE = 24;        // corridor and gutter lane for a pipe: wider than the widest pipe (16 + 4 outline)
  var LINK_LANE = 8;         // lane for a thin information link
  var AUX_LABEL_K = 0.7;     // ... above which auxiliary and input names appear (always for the focused chain)   // ... above which flow names appear (below it, names show on hover and focus)

  function el(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { if (attrs[k] !== null && attrs[k] !== undefined) { e.setAttribute(k, attrs[k]); } });
    if (parent) { parent.appendChild(e); }
    return e;
  }
  function h(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text !== undefined && text !== null) { e.textContent = text; }
    return e;
  }
  function wrap(name, n) {
    var words = name.split(" "), lines = [""];
    words.forEach(function (w) {
      var cur = lines[lines.length - 1];
      if (cur && (cur + " " + w).length > n) { lines.push(w); } else { lines[lines.length - 1] = cur ? cur + " " + w : w; }
    });
    if (lines.length > 3) { lines = lines.slice(0, 2).concat([lines.slice(2).join(" ")]); }
    return lines;
  }
  function label(parent, x, y, name, n, cls, size) {
    var t = el("text", {x: x, y: y, "text-anchor": "middle", "class": cls || "nlabel", style: size ? "font-size:" + size.toFixed(1) + "px" : null}, parent);
    wrap(name, n).forEach(function (line, i) {
      var s = el("tspan", {x: x, dy: i ? "1.15em" : 0}, t);
      s.textContent = line;
    });
    return t;
  }
  function loopCode(name) { return name.split(" ")[0]; }

  function Structure(root, D, hooks) {
    this.D = D;
    this.S = D.structure;
    this.hooks = hooks;
    this.mode = "sfd";
    this.showAll = false;
    this.collapsed = {};
    this.focus = null;
    this.depth = 1;
    this.loop = null;
    this.level = {};
    this.root = root;
    var S = this.S, self = this;
    this.byId = S.nodes;
    this.links = S.links;
    this.out = {};
    this.inn = {};
    S.links.forEach(function (k) {
      (self.out[k.from] = self.out[k.from] || []).push(k);
      (self.inn[k.to] = self.inn[k.to] || []).push(k);
    });
    this.layout = "overview";
    this.canvas = document.getElementById("st-canvas");
    this.svg = el("svg", {"class": "sd-diagram", role: "group", "aria-label": "Model diagram. Tab moves through variables and loop badges; Enter focuses one; Escape clears."}, this.canvas);
    this.mini = el("svg", {"class": "sd-minimap", "aria-hidden": "true"}, document.getElementById("minimap-slot"));
    this.bounds = this.boundsOf(this.layout);
    this.view = Object.assign({}, this.bounds);
    this.bindControls();
    var self2 = this, timer = null;
    document.getElementById("st-time").addEventListener("input", function (e) { self2.setTime(Number(e.target.value), "scrub"); });
    document.getElementById("st-values").addEventListener("change", function () { self2.render(); });
    var play = document.getElementById("st-play");
    play.addEventListener("click", function () {
      if (timer) { clearInterval(timer); timer = null; play.setAttribute("aria-pressed", "false"); play.textContent = "Play"; return; }
      play.setAttribute("aria-pressed", "true");
      play.textContent = "Pause";
      timer = setInterval(function () {
        if (!self2.run || self2.t >= self2.run.time.length - 1) { play.click(); return; }
        self2.setTime(self2.t + 1, "play");
      }, 120);
    });
    SDPooling.init(D.structure);
    if (window.matchMedia && window.matchMedia("(max-width: 760px)").matches) { document.getElementById("st-loops").open = false; }
    this.buildLoopList();
    this.buildLegend();
    this.fit();
    if (typeof ResizeObserver !== "undefined") {
      new ResizeObserver(function () { self.applyView(); }).observe(this.canvas);
    }
  }

  // ---------- two layouts: a compact overview (stocks and flows) and the full detail layout ----------
  // Regions come from the build with region-local node coordinates; the page packs them into rows so the diagram
  // matches the canvas shape (fills both axes), trying every row width a run of consecutive regions can give.
  Structure.prototype.pack = function (mode) {
    var reqs = mode === "detail" ? null : this.routeRequests(mode);
    var cw = this.canvas.clientWidth || 800, ch = this.canvas.clientHeight || 500;
    // fast path: the same requests object (one render) and the same canvas size give the same packing
    var fast = this.packFast && this.packFast[mode];
    if (fast && fast.reqs === reqs && fast.cw === cw && fast.ch === ch) { return fast.pack; }
    reqs = reqs || [];
    var
      key = mode + ":" + cw + "x" + ch + ":" + (mode === "detail" ? "" : reqs.sig);
    this.packs = this.packs || {};
    this.packFast = this.packFast || {};
    if (this.packs[key]) {
      this.packFast[mode] = {reqs: mode === "detail" ? null : reqs, cw: cw, ch: ch, pack: this.packs[key]};
      return this.packs[key];
    }
    var S = this.S, src = mode === "detail" ? S.sectors : S.overview, gap = S.overview_geometry.gap;
    var cands = [Math.max.apply(null, src.map(function (r) { return r.w; }))];
    for (var i = 0; i < src.length; i++) {
      var sum = 0;
      for (var j = i; j < src.length; j++) { sum += src[j].w + (j > i ? gap : 0); cands.push(sum); }
    }
    var best = null;
    cands.forEach(function (W) {
      if (W < cands[0]) { return; }
      var x = 0, y = 0, rowh = 0, wt = 0, out = [];
      src.forEach(function (r) {
        if (x > 0 && x + r.w > W + 0.5) { x = 0; y += rowh + gap; rowh = 0; }
        out.push({sector: r.sector, n: r.n, w: r.w, h: r.h, x: x, y: y});
        wt = Math.max(wt, x + r.w);
        x += r.w + gap;
        rowh = Math.max(rowh, r.h);
      });
      var ht = y + rowh, sc = Math.min(cw / wt, ch / ht), fill = (wt * sc / cw) * (ht * sc / ch);
      if (!best || fill > best.fill + 1e-9) { best = {fill: fill, regions: out}; }
    });
    var rows = [], aspect = cw / ch;
    best.regions.forEach(function (r) {
      var row = rows.filter(function (q) { return Math.abs(q.y - r.y) < 1; })[0];
      if (!row) { row = {y: r.y, items: []}; rows.push(row); }
      row.items.push(r);
    });
    // each row's corridor grows to hold one lane per routed line through it: PIPE_LANE per pipe (wider than the widest
    // pipe), LINK_LANE per thin link; the regions below move down by the same amount
    var rowOf = {};
    rows.forEach(function (row, i) { row.items.forEach(function (r) { rowOf[r.sector] = i; }); row.pipes = 0; row.links = 0; });
    reqs.forEach(function (q) {
      var ra = rowOf[S.nodes[q[0]].sector], rb = rowOf[S.nodes[q[1]].sector];
      [ra, rb].filter(function (x, k, arr) { return x !== undefined && arr.indexOf(x) === k; }).forEach(function (ri) {
        rows[ri][q[2] === "pipe" ? "pipes" : "links"] += 1;
      });
    });
    var shift = 0, corr0 = S.overview_geometry.corridor;
    rows.forEach(function (row, i) {
      var need = 12 + row.pipes * PIPE_LANE + row.links * LINK_LANE, extra = mode === "detail" ? 0 : Math.max(0, need - corr0);
      row.items.forEach(function (r) { r.y += shift; r.h += extra; r.extra = extra; r.row = i; r.corr = corr0 + extra; });
      row.y += shift;
      shift += extra;
    });
    // match the canvas shape: stretch rows sideways (at most 1.6x) when the packing is too narrow, or spread the row
    // gaps when it is too wide; node positions inside a region scale with it
    var wt0 = Math.max.apply(null, best.regions.map(function (r) { return r.x + r.w; }));
    var ht0 = Math.max.apply(null, best.regions.map(function (r) { return r.y + r.h; }));
    best.regions.forEach(function (r) { r.fx = 1; });
    if (wt0 / ht0 < aspect) {
      var target = Math.min(ht0 * aspect, wt0 * 1.6);
      rows.forEach(function (row) {
        var rw = Math.max.apply(null, row.items.map(function (r) { return r.x + r.w; })), f = target / rw;
        row.items.forEach(function (r) { r.x *= f; r.w *= f; r.fx = f; });
      });
    } else if (rows.length > 1) {
      var extra = (wt0 / aspect - ht0) / (rows.length - 1);
      rows.forEach(function (row, i) { row.items.forEach(function (r) { r.y += extra * i; }); });
    }
    var by = {}, pos = {};
    best.regions.forEach(function (r) { by[r.sector] = r; });
    var lx = mode === "detail" ? "lx" : "olx", ly = mode === "detail" ? "ly" : "oly";
    Object.keys(S.nodes).forEach(function (id) {
      var n = S.nodes[id];
      if (n[lx] !== undefined && by[n.sector]) {
        pos[id] = {x: by[n.sector].x + n[lx] * by[n.sector].fx, y: by[n.sector].y + n[ly] + (by[n.sector].extra || 0)};
      }
    });
    var gutterPipes = reqs.filter(function (q) { return q[2] === "pipe" && rowOf[S.nodes[q[0]].sector] !== rowOf[S.nodes[q[1]].sector]; }).length;
    this.packs[key] = {regions: best.regions, by: by, pos: pos, rows: rows, gutterPipes: gutterPipes};
    this.packFast[mode] = {reqs: mode === "detail" ? null : reqs, cw: cw, ch: ch, pack: this.packs[key]};
    return this.packs[key];
  };
  Structure.prototype.regionsOf = function (mode) { return this.pack(mode).regions; };
  Structure.prototype.regions = function () { return this.regionsOf(this.layout); };
  Structure.prototype.regionOf = function (id) { return this.pack(this.layout).by[this.byId[id].sector]; };
  Structure.prototype.P = function (n) {
    var p = this.pack(this.layout).pos[n.id];
    return p ? {x: p.x, y: p.y} : {x: NaN, y: NaN};
  };
  Structure.prototype.boundsOf = function (mode) {
    var rs = this.regionsOf(mode);
    var minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
    rs.forEach(function (r) {
      minx = Math.min(minx, r.x); miny = Math.min(miny, r.y);
      maxx = Math.max(maxx, r.x + r.w); maxy = Math.max(maxy, r.y + r.h);
    });
    var m = 70;   // room for loop badges placed beyond a region's edge
    return {x: minx - m, y: miny - m, w: maxx - minx + 2 * m, h: maxy - miny + 2 * m};
  };

  // ---------- routing at the overview ----------
  // A line between regions never crosses a label or title: it rises from the top of its mark into the region's
  // corridor (an empty band under the title), runs along the corridor, uses the outer gutter to change rows, and drops
  // into the target from above; lines inside one region (or one row) go up, along the corridor and down. Lanes
  // separate parallel lines.
  // the lines that will be routed at the overview (they decide how wide each corridor must be): pipe segments between
  // regions, and every visible link (stock-and-flow view: information links; causal-loop view: all links)
  // a pipe inside one region is routed (not drawn straight) when another stock or valve sits between its ends
  Structure.prototype.blockedInRow = function (aId, bId) {
    var S = this.S, a = S.nodes[aId], b = S.nodes[bId], self = this;
    if (a.sector !== b.sector || a.olx === undefined || b.olx === undefined) { return false; }
    var lo = Math.min(a.olx, b.olx), hi = Math.max(a.olx, b.olx);
    return Object.keys(S.nodes).some(function (id) {
      var n = S.nodes[id];
      return id !== aId && id !== bId && n.sector === a.sector && (n.kind === "stock" || n.kind === "flow") &&
        n.olx !== undefined && n.olx > lo && n.olx < hi && self.visible(id);
    });
  };
  Structure.prototype.routedPipe = function (aId, bId) {
    return this.layout !== "detail" && this.mode === "sfd" &&
      (this.S.nodes[aId].sector !== this.S.nodes[bId].sector || this.blockedInRow(aId, bId));
  };
  Structure.prototype.routeRequests = function (mode) {
    // computed once per render (render clears the memo): pack() is consulted by every position lookup
    this.reqMemo = this.reqMemo || {};
    if (this.reqMemo[mode]) { return this.reqMemo[mode]; }
    var self = this, S = this.S, out = [], saved = this.layout;
    this.layout = mode;
    var vis = function (id) { return self.visible(id); };
    if (this.mode === "sfd") {
      S.pipes.forEach(function (p) {
        if (!vis(p.flow)) { return; }
        p.from.forEach(function (f) { if (vis(f) && self.routedPipe(f, p.flow)) { out.push([f, p.flow, "pipe"]); } });
        p.to.forEach(function (t) { if (vis(t) && self.routedPipe(p.flow, t)) { out.push([p.flow, t, "pipe"]); } });
      });
    }
    this.links.forEach(function (k) {
      if ((self.mode === "sfd" && k.kind === "pipe") || !vis(k.from) || !vis(k.to)) { return; }
      out.push([k.from, k.to, "link"]);
    });
    this.layout = saved;
    out.sig = out.map(function (r) { return r.join(">"); }).join(",");
    this.reqMemo[mode] = out;
    return out;
  };
  // a lane in a row's corridor: pipes first, PIPE_LANE apart, then thin links LINK_LANE apart
  Structure.prototype.lane = function (r, kind) {
    var use = this.laneUse[r.row] = this.laneUse[r.row] || {pipe: 0, link: 0}, rows = this.pack(this.layout).rows;
    var top = r.y + this.S.overview_geometry.title_band + 6;
    if (kind === "pipe") { return top + PIPE_LANE * (use.pipe++ + 0.5); }
    return top + rows[r.row].pipes * PIPE_LANE + LINK_LANE * (use.link++ + 0.5);
  };
  // where a line meets a mark: stocks take successive ports across the tank top; a valve is met from the side
  Structure.prototype.port = function (id) {
    var p = this.top(id), n = this.byId[id], k = this.portUse[id] = (this.portUse[id] || 0) + 1;
    if (n.kind === "stock" && this.mode === "sfd") { p.x += [0, -26, 26, -45, 45, -13, 13][(k - 1) % 7]; }
    return p;
  };
  Structure.prototype.top = function (id) {
    var p = this.P(this.byId[id]), t = this.markTop && this.markTop[id];
    return {x: p.x, y: p.y + (t === undefined ? -28 : t)};
  };
  function poly(pts) {
    var d = "M" + pts.map(function (q) { return q.x.toFixed(1) + "," + q.y.toFixed(1); }).join("L");
    var lens = [0];
    for (var i = 1; i < pts.length; i++) { lens.push(lens[i - 1] + Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y)); }
    var total = lens[lens.length - 1] || 1;
    return {d: d, at: function (t) {
      var L = t * total, i = 1;
      while (i < pts.length - 1 && lens[i] < L) { i++; }
      var a = pts[i - 1], b = pts[i], seg = (lens[i] - lens[i - 1]) || 1, u = (L - lens[i - 1]) / seg;
      return {x: a.x + (b.x - a.x) * u, y: a.y + (b.y - a.y) * u, tx: b.x - a.x, ty: b.y - a.y};
    }};
  }
  Structure.prototype.route = function (aId, bId, kind) {
    kind = kind || "link";
    var ra = this.regionOf(aId), rb = this.regionOf(bId), na = this.byId[aId], nb = this.byId[bId];
    var pipeValve = kind === "pipe" && this.mode === "sfd";
    // a pipe leaves a valve to the right and arrives at one from the left, rising and dropping 40 units to the side
    var a0 = pipeValve && na.kind === "flow" ? this.P(na) : null, b0 = pipeValve && nb.kind === "flow" ? this.P(nb) : null;
    var a = a0 ? {x: a0.x + 40, y: a0.y} : this.port(aId), b = b0 ? {x: b0.x - 40, y: b0.y} : this.port(bId);
    var ya = this.lane(ra, kind), yb = ra.row === rb.row ? ya : this.lane(rb, kind), pts;
    if (ra.row === rb.row) {
      pts = [a, {x: a.x, y: ya}, {x: b.x, y: ya}, b];
    } else {
      var rs = this.regions(), gap = this.S.overview_geometry.gap, g = this.gutterUse;
      var minx = Math.min.apply(null, rs.map(function (r) { return r.x; })), maxx = Math.max.apply(null, rs.map(function (r) { return r.x + r.w; }));
      var left = Math.abs(a.x - minx) + Math.abs(b.x - minx) <= Math.abs(a.x - maxx) + Math.abs(b.x - maxx), side = left ? "l" : "r";
      // pipes take the inner gutter lanes; thin links run outside all of them
      var u = g[side] = g[side] || {pipe: 0, link: 0}, off = kind === "pipe" ? 14 + PIPE_LANE * (u.pipe++ + 0.5) :
        14 + PIPE_LANE * this.pack(this.layout).gutterPipes + LINK_LANE * (u.link++ + 0.5);
      var xg = left ? minx - off : maxx + off;
      pts = [a, {x: a.x, y: ya}, {x: xg, y: ya}, {x: xg, y: yb}, {x: b.x, y: yb}, b];
    }
    if (a0) { pts.unshift({x: a0.x + 10, y: a0.y}); }
    if (b0) { pts.push({x: b0.x - 10, y: b0.y}); }
    return poly(pts);
  };

  // switch layout keeping the same screen scale, centred on the stock or flow nearest the current view centre
  Structure.prototype.setLayout = function (mode, anchorId) {
    if (mode === this.layout) { return; }
    var self = this, v = this.view, cx = v.x + v.w / 2, cy = v.y + v.h / 2, best = anchorId, bd = Infinity;
    if (!best) {
      Object.keys(this.byId).forEach(function (id) {
        var n = self.byId[id];
        if (n.level !== 0) { return; }
        var p = self.P(n), d = (p.x - cx) * (p.x - cx) + (p.y - cy) * (p.y - cy);
        if (d < bd) { bd = d; best = id; }
      });
    }
    this.layout = mode;
    this.bounds = this.boundsOf(mode);
    if (best) { var q = this.P(this.byId[best]); this.view = {x: q.x - v.w / 2, y: q.y - v.h / 2, w: v.w, h: v.h}; }
  };
  Structure.prototype.needDetail = function () { return this.showAll || !!this.force; };

  // ---------- visibility ----------
  Structure.prototype.k = function () {
    var w = this.canvas.clientWidth || 800;
    return w / this.view.w;
  };
  Structure.prototype.visible = function (id) {
    var n = this.byId[id];
    if (this.collapsed[n.sector] && !(this.force && this.force[id])) { return false; }
    if (n.level === 0) { return true; }
    if (this.layout !== "detail") { return false; }
    return this.showAll || this.k() >= DETAIL_OUT_K || !!(this.force && this.force[id]);
  };

  // ---------- geometry ----------
  Structure.prototype.radius = function (n) {
    if (this.mode === "cld") { return n.kind === "stock" ? 34 : 18; }
    return n.kind === "stock" ? 40 : n.kind === "flow" ? 14 : 10;
  };
  Structure.prototype.curve = function (na, nb, bend) {
    var a = this.P(na), b = this.P(nb), ra = this.radius(na), rb = this.radius(nb) + 4;
    var dx = b.x - a.x, dy = b.y - a.y, len = Math.sqrt(dx * dx + dy * dy) || 1;
    var nx = -dy / len, ny = dx / len, c = bend * Math.min(len, 400);
    var cx = (a.x + b.x) / 2 + nx * c, cy = (a.y + b.y) / 2 + ny * c;
    function toward(p, q, r) {
      var ex = q.x - p.x, ey = q.y - p.y, l = Math.sqrt(ex * ex + ey * ey) || 1;
      return {x: p.x + ex / l * r, y: p.y + ey / l * r};
    }
    var s = toward(a, {x: cx, y: cy}, ra), e = toward(b, {x: cx, y: cy}, rb);
    return {d: "M" + s.x.toFixed(1) + "," + s.y.toFixed(1) + "Q" + cx.toFixed(1) + "," + cy.toFixed(1) + " " + e.x.toFixed(1) + "," + e.y.toFixed(1),
      at: function (t) {
        var u = 1 - t;
        return {x: u * u * s.x + 2 * u * t * cx + t * t * e.x, y: u * u * s.y + 2 * u * t * cy + t * t * e.y,
          tx: 2 * u * (cx - s.x) + 2 * t * (e.x - cx), ty: 2 * u * (cy - s.y) + 2 * t * (e.y - cy)};
      }};
  };

  // ---------- live run (M3b) ----------
  // change rule (ripple marks and colours): different from the baseline when max_t |current - baseline| exceeds 1e-6 of
  // the series' scale; at one time, when |current - baseline| exceeds 1e-6 of max(|current|, |baseline|)
  function changeSign(c, b) {
    if (!isFinite(c) || !isFinite(b) || Math.abs(c - b) <= 1e-6 * Math.max(Math.abs(c), Math.abs(b), 1e-12)) { return "0"; }
    return c > b ? "+" : "-";
  }
  Structure.prototype.setRuns = function (run, base, rippleFrom) {
    var self = this, S = this.S;
    this.ltmRes = null;
    this.run = run;
    this.base = base;
    if (this.t === undefined || this.t >= run.time.length) { this.t = this.hooks.defaultTime(run); }
    this.unitScale = {};
    S.pipes.forEach(function (p) {
      var n = self.byId[p.flow], a = run.series[n.name], b = base.series[n.name], mx = 0;
      for (var i = 0; i < a.length; i++) { mx = Math.max(mx, isFinite(a[i]) ? Math.abs(a[i]) : 0, isFinite(b[i]) ? Math.abs(b[i]) : 0); }
      self.unitScale[n.unit] = Math.max(self.unitScale[n.unit] || 0, mx);
    });
    this.changed = {};
    Object.keys(S.nodes).forEach(function (id) {
      var name = S.nodes[id].name, a = run.series[name], b = base.series[name], sc = 0, d = 0;
      for (var i = 0; i < a.length; i++) { sc = Math.max(sc, Math.abs(a[i]), Math.abs(b[i])); d = Math.max(d, Math.abs(a[i] - b[i])); }
      self.changed[id] = sc > 0 && d > 1e-6 * sc;
    });
    if (rippleFrom) {
      var hops = {}, frontier = [rippleFrom];
      hops[rippleFrom] = 0;
      for (var h = 1; frontier.length; h++) {
        var next = [];
        frontier.forEach(function (n) {
          (self.out[n] || []).forEach(function (k) { if (hops[k.to] === undefined) { hops[k.to] = h; next.push(k.to); } });
        });
        frontier = next;
      }
      this.ripple = {hops: hops, at: Date.now()};
    }
  };
  // ---------- link and loop strength (M3c) ----------
  // live: loops-that-matter scores for the current run (ltm.js, checked against loop_detector by the build);
  // precomputed: loop_detector's base-case scores, used only when that check failed, and labelled as such
  Structure.prototype.ltmResult = function () {
    if (this.ltmRes) { return this.ltmRes; }
    var L = this.D.ltm, fix = function (a) { return a === null ? null : a.map(function (x) { return x === null ? NaN : x; }); };
    if (L.mode === "live") {
      this.ltmRes = SDLtm.compute(this.hooks.runDt(), SDEqs, SDEQ_META, SDEngine.META.names, L.loops);
    } else {
      var pre = L.precomputed, links = {};
      Object.keys(pre.links).forEach(function (k) { links[k] = fix(pre.links[k]); });
      this.ltmRes = {time: pre.time, links: links, rel: pre.rel.map(fix)};
    }
    return this.ltmRes;
  };
  Structure.prototype.ltmIndex = function () {
    if (!this.run) { return -1; }
    return this.ltmResult().time.indexOf(this.run.time[this.t]);
  };
  Structure.prototype.ltmSubset = function () {
    var L = this.D.ltm, S = this.S;
    if (L.restrict && this.restrictOn !== false) {
      var stock = L.restrict.stock;
      return S.loops.map(function (lp, i) { return lp.nodes.some(function (n) { return S.nodes[n].name === stock; }) ? i : -1; })
        .filter(function (i) { return i >= 0; });
    }
    return S.loops.map(function (_, i) { return i; });
  };
  Structure.prototype.ltmLabel = function () {
    return this.D.ltm.mode === "live" ? "live, for the current levers" : "precomputed for the base case only";
  };
  Structure.prototype.setTime = function (i, source) {
    if (!this.run) { return; }
    this.t = Math.max(0, Math.min(this.run.time.length - 1, i));
    var r = document.getElementById("st-time");
    r.value = String(this.t);
    this.render();
    if (source !== "chart" && this.hooks.onTime) { this.hooks.onTime(this.t); }
  };
  Structure.prototype.showValues = function () {
    return document.getElementById("st-values").checked || window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  };

  // ---------- render ----------
  Structure.prototype.render = function () {
    var self = this, S = this.S, svg = this.svg;
    this.reqMemo = {};
    // level of detail: text keeps a readable size on screen (at least about 12 px) when zoomed out
    var k = this.k();
    this.lod = {k: k, stockFont: Math.min(40, Math.max(13, 13 / k)), flowLabels: k >= FLOW_LABEL_K,
      sectorFont: Math.min(38, Math.max(13, 12.5 / k)), badge: Math.min(2.6, Math.max(1, 0.9 / k))};
    var keep = document.activeElement && document.activeElement.getAttribute && document.activeElement.getAttribute("data-key");
    svg.textContent = "";
    this.level = {};
    var defs = el("defs", {}, svg);
    var m = el("marker", {id: "sd-arrow", viewBox: "0 0 10 10", refX: 8, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse"}, defs);
    el("path", {d: "M0,0 L10,5 L0,10 z", fill: "var(--diagram-ink)"}, m);
    var mp = el("marker", {id: "sd-pipe-arrow", viewBox: "0 0 10 10", refX: 6, refY: 5, markerWidth: 16, markerHeight: 16,
      markerUnits: "userSpaceOnUse", orient: "auto"}, defs);   // a fixed size, however wide the pipe
    el("path", {d: "M0,0 L10,5 L0,10 z", fill: "var(--pipe)"}, mp);
    var content = el("g", {"class": "content"}, svg);
    var gReg = el("g", {}, content), gHalo = el("g", {}, content), gLink = el("g", {}, content), gPipe = el("g", {}, content),
      gNode = el("g", {}, content), gBadge = el("g", {}, content);
    this.geom = {};
    // sector regions
    this.regions().forEach(function (r) {
      var col = !!self.collapsed[r.sector];
      el("rect", {"class": "region" + (col ? " collapsed" : ""), x: r.x, y: r.y, width: r.w, height: col ? 56 : r.h, rx: 14}, gReg);
      var tg = el("g", {"class": "sector-toggle", tabindex: 0, role: "button", "aria-expanded": String(!col),
        "data-sector": r.sector, "data-key": "sector:" + r.sector,
        "aria-label": "Sector " + r.sector + ", " + r.n + " variables. Press Enter to " + (col ? "expand" : "collapse") + "."}, gReg);
      var fs = Math.min(self.lod.sectorFont, self.layout === "detail" ? 17 : 26);   // the title stays in its band
      el("rect", {x: r.x + 8, y: r.y + 6, width: Math.min(r.w - 16, 30 + (r.sector.length + (col ? 22 : 2)) * fs * 0.66), height: fs * 2.1, rx: 6, "class": "sector-hit"}, tg);
      var t = el("text", {x: r.x + 18, y: r.y + 6 + fs * 1.45, "class": "sector-title", style: "font-size:" + fs.toFixed(1) + "px"}, tg);
      t.textContent = (col ? "▸ " : "▾ ") + r.sector + (col ? " · " + r.n + " variables hidden" : "");
      // a title never runs past its own region: shrink it to the region width, measured from the rendered text
      var tw = t.getBBox().width, room = r.w - 26;
      if (tw > room && tw > 0) {
        fs = fs * room / tw;
        t.setAttribute("style", "font-size:" + fs.toFixed(1) + "px");
        t.setAttribute("y", (r.y + 6 + fs * 1.45).toFixed(1));
        tg.firstChild.setAttribute("width", Math.min(r.w - 16, room + 14));
        tg.firstChild.setAttribute("height", fs * 2.1);
      }
      tg.addEventListener("click", function () { self.toggleSector(r.sector); });
      tg.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); self.toggleSector(r.sector); } });
    });
    var lit = this.litSet();
    // nodes first (their group sits above the lines), so every mark's rendered top is known before lines are routed
    this.markTop = {};
    this.laneUse = {};
    this.portUse = {};
    this.gutterUse = {};
    Object.keys(S.nodes).sort().forEach(function (id) {
      if (!self.visible(id)) { return; }
      var g = self.drawNode(gNode, S.nodes[id], lit);
      // a line attaches above everything the node draws (in the causal-loop view a name can be taller than its box)
      var top = Infinity;
      Array.prototype.forEach.call(g.children, function (c) {
        if (c.classList.contains("hit") || c.tagName === "title") { return; }
        top = Math.min(top, c.getBBox().y);
      });
      if (isFinite(top)) { self.markTop[id] = top - 2; }
    });
    var routed = this.layout !== "detail";
    var ltm = this.run ? this.ltmResult() : null, ltmJ = ltm ? this.ltmIndex() : -1, lsMax = 0;
    if (ltmJ >= 0) {
      Object.keys(ltm.links).forEach(function (e) {
        var v = ltm.links[e] ? ltm.links[e][ltmJ] : NaN;
        if (isFinite(v) && Math.abs(v) < 1e300) { lsMax = Math.max(lsMax, Math.abs(v)); }
      });
    }
    // info links (and, in the causal-loop view, flow -> stock links)
    this.links.forEach(function (k, i) {
      if (self.mode === "sfd" && k.kind === "pipe") { return; }
      var a = self.byId[k.from], b = self.byId[k.to];
      var va = self.visible(k.from), vb = self.visible(k.to);
      if (!va || !vb) {
        self.aggLink(gLink, k, va, vb);
        return;
      }
      var g = routed ? self.route(k.from, k.to) : self.curve(a, b, (k.from < k.to ? 0.12 : -0.12));
      self.geom[k.from + ">" + k.to] = g.d;
      var onLoop = !!self.loop && self.loop.edges.some(function (e) { return e[0] === k.from && e[1] === k.to; });
      var dim = lit && (self.loop ? !onLoop : !(lit[k.from] && lit[k.to]));
      // at the overview, links between sectors appear only on hover, focus or loop isolation (pipes always show)
      var xsec = self.layout !== "detail" && k.kind === "info" && a.sector !== b.sector;
      var lk = el("g", {"class": "lk" + (xsec ? " xsec" : "") + (onLoop ? " on-loop show" : "") + (lit && !dim ? " show" : ""),
        "data-from": k.from, "data-to": k.to}, gLink);
      var p = el("path", {"class": "link" + (dim ? " dim" : "") + (k.sign === "0" ? " inactive" : ""), d: g.d,
        "data-sign": k.sign, "stroke-dasharray": DASH[k.sign], "marker-end": "url(#sd-arrow)"}, lk);
      var tt = el("title", {}, p);
      tt.textContent = a.name + " → " + b.name + ": " + GLYPH[k.sign] + " (" + SIGN_WORD[k.sign] + "; " + METHOD[k.sign_method] + ")" +
        (k.delay ? ". Delay: " + self.delayText(k.delay) : "");
      if (ltmJ >= 0) {
        // link strength: width and opacity follow |link score| relative to the strongest link in the model at that time
        var ser = ltm.links[k.from + ">" + k.to], ls = ser ? ser[ltmJ] : NaN, rel = isFinite(ls) && lsMax > 0 ? Math.abs(ls) / lsMax : 0;
        p.setAttribute("data-ls", isFinite(ls) ? ls : "");
        p.style.strokeWidth = (0.8 + 3.2 * rel).toFixed(2) + "px";
        p.style.strokeOpacity = (0.3 + 0.7 * rel).toFixed(3);
        tt.textContent += ". Link score at " + S.time_unit.toLowerCase() + " " + self.run.time[self.t] + ": " +
          (isFinite(ls) ? SDFormat.fmt(ls) : "not scored") + " (" + self.ltmLabel() + ")";
      }
      var q = g.at(0.78);
      var s = el("text", {"class": "sign" + (dim ? " dim" : ""), x: (q.x + (-q.ty) / Math.hypot(q.tx, q.ty) * 9).toFixed(1),
        y: (q.y + (q.tx) / Math.hypot(q.tx, q.ty) * 9 + 4).toFixed(1), "text-anchor": "middle"}, lk);
      s.textContent = GLYPH[k.sign];
      if (k.delay) {
        var mid = g.at(0.5), len = Math.hypot(mid.tx, mid.ty) || 1, ux = mid.tx / len, uy = mid.ty / len, px = -uy, py = ux;
        var dm = el("g", {"class": "delay-mark" + (dim ? " dim" : ""), "data-delay-stock": k.delay.stock,
          "data-order": k.delay.order, "data-tau": k.delay.tau}, lk);
        [-3, 3].forEach(function (o) {
          el("line", {x1: (mid.x + ux * o - px * 9).toFixed(1), y1: (mid.y + uy * o - py * 9).toFixed(1),
            x2: (mid.x + ux * o + px * 9).toFixed(1), y2: (mid.y + uy * o + py * 9).toFixed(1)}, dm);
        });
        el("title", {}, dm).textContent = "Delay on " + a.name + " → " + b.name + ": " + self.delayText(k.delay);
      }
    });
    // pipes (stock-and-flow view)
    if (this.mode === "sfd") {
      S.pipes.forEach(function (p) {
        if (!self.visible(p.flow)) { return; }
        var vn = self.byId[p.flow], v = self.P(vn);
        var outerG = gPipe;
        if (self.run) {
          // width proportional to |flow| within its unit; dashes move at a speed proportional to |flow|
          var rate = self.run.series[vn.name][self.t], bv = self.base.series[vn.name][self.t], sc = self.unitScale[vn.unit] || 0;
          var wdt = 2 + 14 * (sc > 0 && isFinite(rate) ? Math.abs(rate) / sc : 0), dur = rate && sc > 0 ? 1.2 * sc / Math.abs(rate) : null;
          var chg = changeSign(rate, bv);
          gPipe = el("g", {"class": "pipe-g", "data-flow": p.flow, "data-rate": rate, "data-scale": sc, "data-width": wdt,
            "data-duration": dur === null ? "" : dur, "data-change": chg}, outerG);
          self.live = {w: wdt, dur: dur, rev: rate < 0, chg: chg};
          el("title", {}, gPipe).textContent = vn.name + ": " + SDFormat.fmt(rate) + " " + vn.unit + " at " + self.S.time_unit.toLowerCase() + " " +
            self.run.time[self.t] + " (" + self.hooks.baselineLabel() + ": " + SDFormat.fmt(bv) + ")";
        } else {
          self.live = null;
        }
        // each segment is lit only if its own edge is (loop isolation: the edge is in the loop; focus: both ends lit)
        var segDim = function (stock) {
          if (!lit) { return false; }
          if (self.loop) { return !stock || !self.loop.edges.some(function (e) { return e[0] === p.flow && e[1] === stock; }); }
          return !(lit[p.flow] && (!stock || lit[stock]));
        };
        var cross = function (stockId) {
          return routed && (self.regionOf(stockId) !== self.regionOf(p.flow) || self.blockedInRow(stockId, p.flow));
        };
        var froms = p.from.filter(function (f) { return self.visible(f); });
        if (!p.from.length) {                                  // no source stock at all: a cloud feeds the valve
          var cin = self.cloud(gPipe, v.x - 74, v.y, segDim(null));
          self.pipe(gPipe, cin, {x: v.x, y: v.y}, false, segDim(null));
        }
        froms.forEach(function (f) {                            // one flow can drain more than one stock (a coflow)
          var dim = segDim(f), seg;
          if (cross(f)) {
            seg = self.pipe(gPipe, null, null, false, dim, self.route(f, p.flow, "pipe").d);
          } else {
            seg = self.pipe(gPipe, self.edgePoint(self.byId[f], v), {x: v.x, y: v.y}, false, dim);
          }
          self.geom[p.flow + ">" + f] = seg;                    // an outflow is drawn as the pipe leaving its stock
        });
        var tos = p.to.filter(function (t) { return self.visible(t); });
        if (!p.to.length) {
          var c = self.cloud(gPipe, v.x + 74, v.y, segDim(null));
          self.pipe(gPipe, {x: v.x, y: v.y}, c, true, segDim(null));
        }
        tos.forEach(function (t) {
          if (cross(t)) {
            self.geom[p.flow + ">" + t] = self.pipe(gPipe, null, null, true, segDim(t), self.route(p.flow, t, "pipe").d);
            return;
          }
          var end = self.edgePoint(self.byId[t], v);
          self.geom[p.flow + ">" + t] = self.pipe(gPipe, {x: v.x, y: v.y}, end, true, segDim(t));
        });
        if (self.live && self.showValues() && self.lod) {
          var vfs = Math.min(30, Math.max(11.5, 11 / self.lod.k));   // readable on screen at any zoom
          var fv = el("text", {"class": "flow-value", x: v.x, y: v.y - 18 - vfs * 0.25, "text-anchor": "middle", style: "font-size:" + vfs.toFixed(1) + "px"}, gPipe);
          fv.textContent = (self.live.chg === "+" ? "▲ " : self.live.chg === "-" ? "▼ " : "") + SDFormat.fmt(self.run.series[vn.name][self.t]);
        }
        gPipe = outerG;
      });
    }
    // loop halos (isolation)
    if (this.loop) {
      this.loop.edges.forEach(function (e) {
        var d = self.geom[e[0] + ">" + e[1]];
        if (d) {
          el("path", {"class": "loop-halo " + (self.loop.polarity === "R" ? "halo-r" : "halo-b"), d: d}, gHalo);
        }
      });
    }
    // loop badges: each at the free spot nearest its loop's centre (rings of candidate positions), clear of node boxes,
    // their labels and badges already placed
    // obstacles are the rendered boxes (getBBox) of every node with its label, and of every sector title. Placement
    // depends only on the drawing's geometry (layout, mode, zoom, sectors, focus), not on the run or the time shown,
    // so it is cached and reused while those stay the same.
    var cw = this.canvas.clientWidth, chh = this.canvas.clientHeight;
    var gkey = [this.layout, this.mode, this.view.w.toFixed(2), cw, chh, JSON.stringify(this.collapsed), this.showAll,
      this.focus || "", this.loop ? this.loop.id : "", this.depth].join("|");
    var cache = this.badgeCache && this.badgeCache.key === gkey ? this.badgeCache.pos : null;
    var obstacles = [];
    Array.prototype.forEach.call(gNode.childNodes, function (g) {
      var n = self.byId[g.getAttribute("data-key").slice(5)], p = self.P(n), b = g.getBBox();
      obstacles.push([p.x + b.x - 3, p.y + b.y - 3, p.x + b.x + b.width + 3, p.y + b.y + b.height + 3]);
    });
    Array.prototype.forEach.call(gReg.querySelectorAll(".sector-toggle text"), function (t) {
      var b = t.getBBox();
      obstacles.push([b.x - 3, b.y - 3, b.x + b.width + 3, b.y + b.height + 3]);
    });
    // every drawn pipe and visible link, sampled every 8 units, so a badge never sits on a line
    if (!cache) Array.prototype.forEach.call(content.querySelectorAll("path.pipe-outer, g.lk:not(.xsec) path.link, g.lk.show path.link, path.agg"), function (path) {
      var L = path.getTotalLength();
      for (var d = 0; d <= L; d += 8) {
        var q = path.getPointAtLength(d);
        obstacles.push([q.x - 6, q.y - 6, q.x + 6, q.y + 6]);
      }
    });
    function free(x, y, r) {
      for (var i = 0; i < obstacles.length; i++) {
        var o = obstacles[i];
        if (x + r > o[0] && x - r < o[2] && y + r > o[1] && y - r < o[3]) { return false; }
      }
      return true;
    }
    var placedNow = {}, meterSub = ltmJ >= 0 ? this.ltmSubset() : [], meterTot = 0;
    meterSub.forEach(function (i) { var v = ltm.rel[i] ? ltm.rel[i][ltmJ] : NaN; if (isFinite(v)) { meterTot += Math.abs(v); } });
    S.loops.forEach(function (lp) {
      var ps = lp.nodes.map(function (n) { return self.P(self.byId[n]); }).filter(function (q) { return isFinite(q.x); });
      if (!ps.length) { return; }
      var bp = {x: ps.reduce(function (t, q) { return t + q.x; }, 0) / ps.length, y: ps.reduce(function (t, q) { return t + q.y; }, 0) / ps.length};
      var r = 19.5 * self.lod.badge, x = bp.x, y = bp.y, found = cache ? true : free(x, y, r);
      if (cache && cache[lp.id]) { x = cache[lp.id][0]; y = cache[lp.id][1]; }
      for (var ring = 1; ring < 40 && !found; ring++) {
        var steps = 8 * ring;
        for (var j = 0; j < steps && !found; j++) {
          var a = j / steps * 2 * Math.PI, cx = bp.x + Math.cos(a) * ring * r * 1.6, cy = bp.y + Math.sin(a) * ring * r * 1.6;
          if (free(cx, cy, r)) { x = cx; y = cy; found = true; }
        }
      }
      obstacles.push([x - r, y - r, x + r, y + r]);
      placedNow[lp.id] = [x, y];
      var isR = lp.polarity === "R", on = self.loop === lp;
      var dim = (self.loop && !on) || (lit && !self.loop && !lp.nodes.some(function (n) { return lit[n]; }));
      var outView = ltmJ >= 0 && meterSub.indexOf(S.loops.indexOf(lp)) < 0;
      var g = el("g", {"class": "loop-badge" + (isR ? " r" : " b") + (on ? " on" : "") + (dim ? " dim" : "") + (outView ? " outview" : ""),
        tabindex: 0, role: "button", "data-loop-name": lp.name, "data-key": "loop:" + lp.id,
        "aria-pressed": String(on), transform: "translate(" + x.toFixed(1) + "," + y.toFixed(1) + ") scale(" + self.lod.badge.toFixed(2) + ")",
        "aria-label": "Loop " + lp.name + ", " + (isR ? "reinforcing" : "balancing") + ", " + lp.nodes.length +
          " variables. Press Enter to " + (on ? "show all loops" : "isolate it") + "."}, gBadge);
      el("circle", {r: 17, "class": "badge-bg"}, g);
      if (ltmJ >= 0) {
        // loop strength meter: the loop's share of strength among the loops shown in the Loop strength tab (all loops, or
        // the restricted set). A loop outside that set has no share there: no meter, faded, marked "not in this view".
        var li = S.loops.indexOf(lp), rv = ltm.rel[li] ? ltm.rel[li][ltmJ] : NaN;
        var share = !outView && isFinite(rv) && meterTot > 0 ? Math.abs(rv) / meterTot : 0;
        g.setAttribute("data-rel", isFinite(rv) ? rv : "");
        if (!outView) {
          el("rect", {"class": "meter-bg", x: -18, y: 21, width: 36, height: 5, rx: 2}, g);
          el("rect", {"class": "meter", x: -18, y: 21, width: (36 * share).toFixed(2), height: 5, rx: 2}, g);
        }
        g.setAttribute("aria-label", g.getAttribute("aria-label") + " Strength at " + S.time_unit.toLowerCase() + " " +
          self.run.time[self.t] + ": " + (outView ? "not in this view (outside the " + self.D.ltm.restrict.label + " loops)" :
          isFinite(rv) ? SDFormat.fmt(share * 100) + "% share among the loops shown" : "not scored") + " (" + self.ltmLabel() + ").");
      }
      var t = el("text", {y: 4.5, "text-anchor": "middle", "class": "badge-text"}, g);
      t.textContent = loopCode(lp.name);
      el("title", {}, g).textContent = lp.name + " (" + (isR ? "reinforcing" : "balancing") + ")" + (outView ? ": not in this view" : "");
      g.addEventListener("click", function () { self.isolate(lp); });
      g.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); self.isolate(lp); } });
    });
    this.badgeCache = {key: gkey, pos: placedNow};
    this.applyView();
    this.renderMini();
    this.syncLoopList();
    this.renderLive();
    if (keep) {
      var back = svg.querySelector("[data-key='" + keep.replace(/'/g, "\\'") + "']");
      if (back) { back.focus(); }
    }
  };

  Structure.prototype.delayText = function (d) {
    return (d.order === 1 ? "first-order" : "order " + d.order) + " " + d.type + " delay through the stock " + d.stock +
      " (" + d.order + " stock" + (d.order === 1 ? "" : "s") + "), time constant " + d.tau + " = " +
      SDFormat.fmt(d.tau_base) + " " + this.S.time_unit + " at t = 0" +
      (d.tau_run && d.tau_run[0] !== d.tau_run[1] ? " (" + SDFormat.fmt(d.tau_run[0]) + "–" + SDFormat.fmt(d.tau_run[1]) + " over the base run)" : "") +
      "; form: " + d.form.replace("_", " ") + " (delay audit)";
  };

  Structure.prototype.edgePoint = function (sn, toward) {
    var stock = this.P(sn), w = 52, hh = 28, dx = toward.x - stock.x, dy = toward.y - stock.y;
    if (Math.abs(dx) * hh > Math.abs(dy) * w) { return {x: stock.x + (dx > 0 ? w : -w), y: stock.y}; }
    return {x: stock.x, y: stock.y + (dy > 0 ? hh : -hh)};
  };
  Structure.prototype.pipeLive = function (g, d, dim) {
    var L = this.live;
    if (!L) { return; }
    g.lastChild.previousSibling.setAttribute("style", "stroke-width:" + (L.w + 4).toFixed(2) + "px");
    g.lastChild.setAttribute("style", "stroke-width:" + L.w.toFixed(2) + "px");
    var f = el("path", {"class": "pipe-flow chg-" + ({"+": "up", "-": "down", "0": "none"})[L.chg] + (L.dur === null ? " still" : "") + (dim ? " dim" : ""), d: d}, g);
    f.setAttribute("style", "stroke-width:" + Math.max(1.5, L.w * 0.45).toFixed(2) + "px" +
      (L.dur === null ? "" : ";animation-duration:" + L.dur + "s" + (L.rev ? ";animation-direction:reverse" : "")));
  };
  Structure.prototype.pipe = function (g, a, b, arrow, dim, dRouted) {
    if (dRouted) {
      el("path", {"class": "pipe-outer" + (dim ? " dim" : ""), d: dRouted}, g);
      el("path", {"class": "pipe-inner" + (dim ? " dim" : ""), d: dRouted, "marker-end": arrow ? "url(#sd-pipe-arrow)" : null}, g);
      this.pipeLive(g, dRouted, dim);
      return dRouted;
    }
    var mx = (a.x + b.x) / 2, self = this, d;
    // a straight pipe that would run behind another stock or valve on the same row arcs over it instead
    var blocked = Math.abs(a.y - b.y) < 2 && Object.keys(this.byId).some(function (id) {
      var n = self.byId[id];
      if ((n.kind !== "stock" && n.kind !== "flow") || !self.visible(id)) { return false; }
      var p = self.P(n), half = n.kind === "stock" ? 52 : 12;
      return Math.abs(p.y - a.y) < 30 && p.x - half > Math.min(a.x, b.x) + 1 && p.x + half < Math.max(a.x, b.x) - 1;
    });
    if (blocked) {
      d = "M" + a.x + "," + a.y + "C" + a.x + "," + (a.y - 70) + " " + b.x + "," + (b.y - 70) + " " + b.x + "," + b.y;
    } else {
      d = Math.abs(a.y - b.y) < 2 ? "M" + a.x + "," + a.y + "L" + b.x + "," + b.y :
        "M" + a.x + "," + a.y + "C" + mx + "," + a.y + " " + mx + "," + b.y + " " + b.x + "," + b.y;
    }
    el("path", {"class": "pipe-outer" + (dim ? " dim" : ""), d: d}, g);
    el("path", {"class": "pipe-inner" + (dim ? " dim" : ""), d: d, "marker-end": arrow ? "url(#sd-pipe-arrow)" : null}, g);
    this.pipeLive(g, d, dim);
    return d;
  };
  Structure.prototype.cloud = function (g, x, y, dim) {
    var c = el("g", {"class": "cloud" + (dim ? " dim" : ""), transform: "translate(" + x + "," + y + ")"}, g);
    el("path", {d: "M-16,6 a7,7 0 0 1 2,-13 a9,9 0 0 1 16,-3 a7,7 0 0 1 12,6 a6,6 0 0 1 -2,12 z"}, c);
    el("title", {}, c).textContent = "Cloud: source or sink outside the model boundary";
    return {x: x, y: y};
  };

  Structure.prototype.drawNode = function (g, n, lit) {
    var self = this, dim = lit && !lit[n.id], sel = this.focus === n.id;
    var grp = el("g", {"class": "node " + n.kind + (n.exogenous ? " exo" : "") + (dim ? " dim" : "") + (lit && lit[n.id] ? " lit" : "") + (sel ? " selected" : ""),
      tabindex: 0, role: "button", "data-name": n.name, "data-kind": n.kind, "data-key": "node:" + n.id,
      transform: "translate(" + this.P(n).x + "," + this.P(n).y + ")",
      "aria-label": n.name + ", " + n.kind + (n.exogenous ? " (exogenous input)" : "") + ", " + SDFormat.unitText(n.unit) + ". Press Enter to focus its chain."}, g);
    var live = null;
    if (this.run) {
      grp.setAttribute("data-changed", this.changed[n.id] ? "true" : "false");
      if (this.changed[n.id]) { grp.classList.add("changed"); }
      var a = this.run.series[n.name], b = this.base.series[n.name], mx = 0;
      for (var q = 0; q < a.length; q++) { mx = Math.max(mx, Math.abs(a[q]), Math.abs(b[q])); }
      live = {cur: a[this.t], base: b[this.t], level: mx > 0 ? Math.abs(a[this.t]) / mx : 0, ghost: mx > 0 ? Math.abs(b[this.t]) / mx : 0,
        chg: changeSign(a[this.t], b[this.t])};
      if (n.kind === "stock") {
        grp.setAttribute("data-level", live.level);
        grp.setAttribute("data-ghost", live.ghost);
        grp.setAttribute("data-change", live.chg);
      }
      // ripple: a pulse travels outward from the moved lever, one hop at a time (none under reduced motion)
      if (this.ripple && this.ripple.hops[n.id] !== undefined && Date.now() - this.ripple.at < 2500) {
        var delay = (this.ripple.hops[n.id] * 0.12).toFixed(2) + "s";
        grp.classList.add("ripple");
        grp.style.animationDelay = delay;
        el("circle", {"class": "ripple-ring", r: 34, style: "animation-delay:" + delay}, grp);
      }
    }
    if (this.mode === "cld") {
      if (n.kind === "stock") { el("rect", {x: -46, y: -16, width: 92, height: 32, rx: 6, "class": "cld-stock"}, grp); }
      var showName = n.kind === "stock" || (n.kind === "flow" ? this.lod.flowLabels : this.lod.k >= AUX_LABEL_K) || sel || (lit && lit[n.id]);
      if (showName) {
        label(grp, 0, n.kind === "stock" ? -2 : 4, n.name, 16, "nlabel" + (n.kind === "stock" ? " stock-label" : "") + (n.exogenous ? " exo-label" : ""),
          n.kind === "stock" ? this.lod.stockFont : Math.max(12.5, 11 / this.lod.k));
      } else {
        el("circle", {"class": "aux" + (n.exogenous ? " exo" : ""), r: 6}, grp);
      }
    } else if (n.kind === "stock") {
      el("rect", {"class": "tank", x: -52, y: -28, width: 104, height: 56, rx: 7}, grp);
      if (live) {
        // level and the baseline's ghost on one scale (the larger of either run's peak); colour and glyph = change
        var hgt = Math.max(0, Math.min(1, live.level)) * 52, gy = 26 - Math.max(0, Math.min(1, live.ghost)) * 52;
        el("rect", {"class": "tank-fill chg-" + ({"+": "up", "-": "down", "0": "none"})[live.chg], x: -50, y: 26 - hgt, width: 100, height: hgt, rx: 5}, grp);
        el("line", {"class": "tank-ghost", x1: -50, y1: gy, x2: 50, y2: gy}, grp);
        if (live.chg !== "0") {
          el("text", {"class": "chg-glyph", x: 44, y: -12, "text-anchor": "end"}, grp).textContent = live.chg === "+" ? "▲" : "▼";
        }
      }
      var f = this.lod.stockFont;
      label(grp, 0, f > 14 ? 28 + f * 1.05 : -6, n.name, 14, "nlabel stock-label", f);
    } else if (n.kind === "flow") {
      el("path", {"class": "valve", d: "M-10,-8 L10,8 L10,-8 L-10,8 Z"}, grp);
      el("line", {"class": "valve-stem", x1: 0, y1: -8, x2: 0, y2: -15}, grp);
      if (this.lod.flowLabels) { label(grp, 0, 26, n.name, 18, "nlabel", Math.max(12.5, 11 / this.lod.k)); }
    } else {
      el("circle", {"class": "aux" + (n.exogenous ? " exo" : ""), r: 7}, grp);
      if (this.lod.k >= AUX_LABEL_K || sel || (lit && lit[n.id])) {
        label(grp, 0, 22, n.name, 18, "nlabel" + (n.exogenous ? " exo-label" : ""), Math.max(12.5, 11 / this.lod.k));
      }
    }
    // a stock's name never grows wider than its cell (at the overview a neighbour's mark sits one cell away)
    var sl = grp.querySelector("text.stock-label");
    if (sl && this.layout !== "detail") {
      var fx = (this.pack(this.layout).by[n.sector] || {fx: 1}).fx, room = 1.75 * 150 * fx * 0.5 * 2 - 24, w = sl.getBBox().width;
      if (w > room) {
        var f0 = parseFloat(sl.style.fontSize) || 12.5, f1 = f0 * room / w, y0 = parseFloat(sl.getAttribute("y"));
        sl.style.fontSize = f1.toFixed(1) + "px";
        if (this.mode !== "cld" && f0 > 14) { sl.setAttribute("y", (y0 - f0 * 1.05 + f1 * 1.05).toFixed(1)); }
      }
    }
    el("title", {}, grp).textContent = n.name + " (" + n.kind + (n.exogenous ? ", exogenous input" : "") + ")";
    // hit area: the whole box of the mark and its name, so the target is larger than the mark
    var hb = grp.getBBox();
    if (hb.width) { grp.insertBefore(el("rect", {"class": "hit", x: hb.x - 4, y: hb.y - 4, width: hb.width + 8, height: hb.height + 8}), grp.firstChild); }
    grp.addEventListener("click", function (e) { e.stopPropagation(); self.setFocus(n.id); });
    grp.addEventListener("pointerenter", function () { self.hoverLinks(n.id, true); });
    grp.addEventListener("pointerleave", function () { self.hoverLinks(n.id, false); });
    grp.addEventListener("focus", function () { self.hoverLinks(n.id, true); });
    grp.addEventListener("blur", function () { self.hoverLinks(n.id, false); });
    grp.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); self.setFocus(n.id); }
    });
    return grp;
  };

  Structure.prototype.hoverLinks = function (id, on) {
    Array.prototype.forEach.call(this.svg.querySelectorAll("g.lk.xsec"), function (g) {
      if (g.getAttribute("data-from") === id || g.getAttribute("data-to") === id) { g.classList.toggle("hover", on); }
    });
  };

  Structure.prototype.aggLink = function (g, k, va, vb) {
    // a link to or from a collapsed sector is drawn to the sector's title once per pair (no sign: it may bundle several)
    var a = this.byId[k.from], b = this.byId[k.to];
    var ca = !va && this.collapsed[a.sector], cb = !vb && this.collapsed[b.sector];
    if ((!va && !ca) || (!vb && !cb) || (ca && cb && a.sector === b.sector)) { return; }
    var key = (ca ? "s:" + a.sector : k.from) + ">" + (cb ? "s:" + b.sector : k.to);
    this.aggSeen = this.aggSeen || {};
    if (this.aggSeen[key] === this.renderId) { return; }
    this.aggSeen[key] = this.renderId;
    var reg = function (sec) { return this.regions().filter(function (r) { return r.sector === sec; })[0]; }.bind(this);
    if ((ca && !reg(a.sector)) || (cb && !reg(b.sector))) { return; }
    var pa = ca ? {x: reg(a.sector).x + 120, y: reg(a.sector).y + 28} : this.P(a);
    var pb = cb ? {x: reg(b.sector).x + 120, y: reg(b.sector).y + 28} : this.P(b);
    el("path", {"class": "agg", d: "M" + pa.x + "," + pa.y + "L" + pb.x + "," + pb.y, "marker-end": "url(#sd-arrow)"}, g);
  };

  // ---------- focus mode and loops ----------
  Structure.prototype.litSet = function () {
    this.renderId = (this.renderId || 0) + 1;
    if (this.loop) {
      var s = {};
      this.loop.nodes.forEach(function (n) { s[n] = true; });
      return s;
    }
    if (!this.focus) { return null; }
    var lit = {}, self = this;
    lit[this.focus] = true;
    function walk(start, dir, depth) {
      var frontier = [start];
      for (var d = 0; d < depth && frontier.length; d++) {
        var next = [];
        frontier.forEach(function (n) {
          ((dir === "up" ? self.inn[n] : self.out[n]) || []).forEach(function (k) {
            var m = dir === "up" ? k.from : k.to;
            if (!lit[m]) { lit[m] = true; next.push(m); }
          });
        });
        frontier = next;
      }
    }
    var depth = this.depth === "all" ? 1e9 : this.depth;
    walk(this.focus, "up", depth);
    walk(this.focus, "down", depth);
    return lit;
  };
  Structure.prototype.setFocus = function (id) {
    this.loop = null;
    this.focus = id;
    this.force = this.litSet();
    this.setLayout("detail", id);
    var c = this.P(this.byId[id]);
    this.view.x = c.x - this.view.w / 2;
    this.view.y = c.y - this.view.h / 2;
    this.render();
    this.detailNode(id);
  };
  Structure.prototype.isolate = function (lp) {
    if (this.loop === lp) { this.clear(); return; }
    this.focus = null;
    this.loop = lp;
    this.force = {};
    lp.nodes.forEach(function (n) { this.force[n] = true; }, this);
    this.setLayout("detail", lp.nodes.filter(function (n) { return this.byId[n].level === 0; }, this)[0]);
    this.render();
    this.detailLoop(lp);
  };
  Structure.prototype.clear = function () {
    this.focus = null;
    this.loop = null;
    this.force = null;
    if (!this.needDetail() && this.k() < SEMANTIC_K) { this.setLayout("overview"); }
    this.render();
    this.detailEmpty();
  };

  Structure.prototype.detailEmpty = function () {
    var d = document.getElementById("structure-detail");
    d.textContent = "";
    d.appendChild(h("p", "muted", "Select a variable (click, or Tab then Enter) to light up what drives it and what it drives, or a loop badge to isolate that loop. Escape clears."));
  };
  Structure.prototype.detailNode = function (id) {
    var self = this, n = this.byId[id], d = document.getElementById("structure-detail");
    d.textContent = "";
    var head = h("div", "detail-head");
    head.appendChild(h("h3", null, n.name + " · " + n.kind + (n.exogenous ? " (exogenous input)" : "")));
    var clr = h("button", "btn btn-quiet", "Clear");
    clr.type = "button";
    clr.addEventListener("click", function () { self.clear(); });
    head.appendChild(clr);
    d.appendChild(head);
    var depth = h("label", "depth");
    depth.appendChild(document.createTextNode("Chain depth "));
    var sel = h("select");
    [["1", "1 step"], ["2", "2 steps"], ["all", "full chain"]].forEach(function (o) {
      var op = h("option", null, o[1]);
      op.value = o[0];
      if (String(self.depth) === o[0]) { op.selected = true; }
      sel.appendChild(op);
    });
    sel.addEventListener("change", function () { self.depth = sel.value === "all" ? "all" : Number(sel.value); self.setFocus(id); });
    depth.appendChild(sel);
    d.appendChild(depth);
    d.appendChild(this.hooks.infoCard(n.name));
    function list(title, links, other) {
      if (!links || !links.length) { return; }
      d.appendChild(h("h4", null, title));
      var ul = h("ul", "detail-links");
      links.forEach(function (k) {
        var li = h("li");
        li.appendChild(h("span", "glyph", GLYPH[k.sign]));
        li.appendChild(document.createTextNode(" " + self.byId[other(k)].name + (k.delay ? " (through a delay)" : "")));
        ul.appendChild(li);
      });
      d.appendChild(ul);
    }
    list("Driven by", this.inn[id], function (k) { return k.from; });
    list("Drives", this.out[id], function (k) { return k.to; });
    var loops = this.S.loops.filter(function (lp) { return lp.nodes.indexOf(id) >= 0; });
    if (loops.length) {
      d.appendChild(h("h4", null, "Loops through " + n.name));
      var ul = h("ul", "detail-loops");
      loops.forEach(function (lp) {
        var li = h("li"), b = h("button", "btn btn-quiet", lp.name);
        b.type = "button";
        b.addEventListener("click", function () { self.isolate(lp); });
        li.appendChild(b);
        ul.appendChild(li);
      });
      d.appendChild(ul);
    }
  };
  Structure.prototype.detailLoop = function (lp) {
    var self = this, d = document.getElementById("structure-detail");
    d.textContent = "";
    var head = h("div", "detail-head");
    head.appendChild(h("h3", null, lp.name + " · " + (lp.polarity === "R" ? "reinforcing" : "balancing")));
    var clr = h("button", "btn btn-quiet", "Show all loops");
    clr.type = "button";
    clr.addEventListener("click", function () { self.clear(); });
    head.appendChild(clr);
    d.appendChild(head);
    d.appendChild(h("p", "muted", lp.polarity === "R" ?
      "Reinforcing: a change travelling round the loop comes back in the same direction (an even number of negative links)." :
      "Balancing: a change travelling round the loop comes back opposed (an odd number of negative links)."));
    var ol = h("ol", "loop-path");
    lp.edges.forEach(function (e) {
      var k = self.links.filter(function (x) { return x.from === e[0] && x.to === e[1]; })[0];
      var li = h("li");
      li.appendChild(document.createTextNode(self.byId[e[0]].name + " "));
      li.appendChild(h("span", "glyph", "→" + GLYPH[k.sign]));
      li.appendChild(document.createTextNode(" " + self.byId[e[1]].name + (k.delay ? " (delay: " + k.delay.tau + ")" : "")));
      ol.appendChild(li);
    });
    d.appendChild(ol);
    d.appendChild(h("p", "muted", "Loop and polarity from the validated loop analysis (loop_dominance.json); name from validation.toml."));
  };

  // ---------- sectors, view, minimap ----------
  Structure.prototype.toggleSector = function (sec) {
    this.collapsed[sec] = !this.collapsed[sec];
    this.render();
    var t = this.svg.querySelector(".sector-toggle[data-sector='" + sec.replace(/'/g, "\\'") + "']");
    if (t) { t.focus(); }
  };
  // fit: frame the rendered content (its getBBox) with a small margin. Text size depends on the zoom, so the frame is
  // measured, applied and re-measured; a last union guarantees nothing is clipped.
  Structure.prototype.fit = function () {
    this.layout = this.needDetail() ? "detail" : "overview";
    this.bounds = this.boundsOf(this.layout);
    this.view = Object.assign({}, this.bounds);
    var cw = this.canvas.clientWidth || 800, ch = this.canvas.clientHeight || 500, self = this;
    function frame(b) {
      var m = Math.max(10, 0.02 * Math.max(b.width, b.height));
      var w = Math.max(b.width + 2 * m, (b.height + 2 * m) * cw / ch), hgt = w * ch / cw;
      self.view = {x: b.x + b.width / 2 - w / 2, y: b.y + b.height / 2 - hgt / 2, w: w, h: hgt};
    }
    for (var i = 0; i < 3; i++) {
      this.render();
      var b = this.svg.querySelector("g.content").getBBox();
      if (!b.width) { return; }
      frame(b);
    }
    this.render();
    var c = this.svg.querySelector("g.content").getBBox(), v = this.view;
    var x0 = Math.min(v.x, c.x - 4), y0 = Math.min(v.y, c.y - 4);
    var x1 = Math.max(v.x + v.w, c.x + c.width + 4), y1 = Math.max(v.y + v.h, c.y + c.height + 4);
    if (x0 < v.x || y0 < v.y || x1 > v.x + v.w || y1 > v.y + v.h) {
      frame({x: x0, y: y0, width: x1 - x0, height: y1 - y0});
      this.applyView();
      this.renderMini();
    }
    this.bounds = Object.assign({}, this.view);
  };
  Structure.prototype.zoom = function (f, cx, cy) {
    var v = this.view;
    cx = cx === undefined ? v.x + v.w / 2 : cx;
    cy = cy === undefined ? v.y + v.h / 2 : cy;
    var w = Math.max(200, Math.min(this.bounds.w * 3, v.w / f));
    var r = w / v.w;
    this.view = {x: cx - (cx - v.x) * r, y: cy - (cy - v.y) * r, w: w, h: v.h * r};
    this.applyView();
    if (this.layout === "overview" && this.k() >= SEMANTIC_K) { this.setLayout("detail"); }
    else if (this.layout === "detail" && !this.needDetail() && this.k() < DETAIL_OUT_K) { this.setLayout("overview"); }
    this.applyView();
    this.render();
  };
  Structure.prototype.pan = function (dx, dy) {
    this.view.x += dx;
    this.view.y += dy;
    this.applyView();
    this.renderMini();
  };
  Structure.prototype.center = function (x, y) {
    this.view.x = x - this.view.w / 2;
    this.view.y = y - this.view.h / 2;
    this.applyView();
    this.renderMini();
  };
  Structure.prototype.applyView = function () {
    var cw = this.canvas.clientWidth || 800, ch = this.canvas.clientHeight || 500, v = this.view;
    var hgt = v.w * ch / cw;
    v.y += (v.h - hgt) / 2;
    v.h = hgt;
    this.svg.setAttribute("viewBox", [v.x, v.y, v.w, v.h].map(function (x) { return x.toFixed(1); }).join(" "));
  };
  Structure.prototype.renderMini = function () {
    var b = this.bounds, mini = this.mini, self = this;
    mini.setAttribute("viewBox", [b.x, b.y, b.w, b.h].join(" "));
    mini.textContent = "";
    this.regions().forEach(function (r) {
      el("rect", {"class": "mini-region", x: r.x, y: r.y, width: r.w, height: self.collapsed[r.sector] ? 56 : r.h, rx: 14}, mini);
    });
    var v = this.view;
    el("rect", {"class": "viewport", x: v.x, y: v.y, width: v.w, height: v.h}, mini);
  };

  // ---------- controls ----------
  Structure.prototype.bindControls = function () {
    var self = this;
    function on(id, ev, f) { document.getElementById(id).addEventListener(ev, f); }
    on("mode-sfd", "click", function () { self.setMode("sfd"); });
    on("mode-cld", "click", function () { self.setMode("cld"); });
    on("show-all", "change", function (e) {
      self.showAll = e.target.checked;
      if (self.showAll) { self.setLayout("detail"); self.view = Object.assign({}, self.boundsOf("detail")); }
      self.fit();
    });
    on("zoom-in", "click", function () { self.zoom(1.4); });
    on("zoom-out", "click", function () { self.zoom(1 / 1.4); });
    on("zoom-fit", "click", function () { self.fit(); });
    on("structure-clear", "click", function () { self.clear(); });
    // side panel tabs: Details (selection, pooling, loops, delays, legend) and Loop strength (timeline, dominant loops)
    var sideTabs = [document.getElementById("side-tab-details"), document.getElementById("side-tab-strength")];
    function sideSelect(k, focus) {
      sideTabs.forEach(function (t, i) {
        t.setAttribute("aria-selected", String(i === k));
        t.tabIndex = i === k ? 0 : -1;
        document.getElementById(t.getAttribute("aria-controls")).hidden = i !== k;
      });
      document.querySelector(".st-side").scrollTop = 0;
      if (focus) { sideTabs[k].focus(); }
    }
    sideTabs.forEach(function (t, i) {
      t.addEventListener("click", function () { sideSelect(i); });
      t.addEventListener("keydown", function (e) {
        var d = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 :
          e.key === "Home" ? -i : e.key === "End" ? sideTabs.length - 1 - i : 0;
        if (!d) { return; }
        e.preventDefault();
        sideSelect((i + d + sideTabs.length) % sideTabs.length, true);
      });
    });
    on("collapse-all", "click", function () { self.regions().forEach(function (r) { self.collapsed[r.sector] = true; }); self.render(); });
    on("expand-all", "click", function () { self.collapsed = {}; self.render(); });
    var input = document.getElementById("structure-search"), res = document.getElementById("search-results");
    input.addEventListener("input", function () {
      var q = input.value.trim().toLowerCase();
      res.textContent = "";
      if (!q) { return; }
      Object.keys(self.byId).map(function (k) { return self.byId[k]; })
        .filter(function (n) { return n.name.toLowerCase().indexOf(q) >= 0; })
        .sort(function (a, b) { return a.name.toLowerCase().indexOf(q) - b.name.toLowerCase().indexOf(q) || a.name.localeCompare(b.name); })
        .slice(0, 8).forEach(function (n) {
          var b = h("button", "btn btn-quiet", n.name + " (" + n.kind + ")");
          b.type = "button";
          b.addEventListener("click", function () {
            res.textContent = "";
            input.value = "";
            if (self.collapsed[n.sector]) { self.collapsed[n.sector] = false; }
            self.setFocus(n.id);
            self.center(self.P(n).x, self.P(n).y);
            var f = self.svg.querySelector("[data-key='node:" + n.id + "']");
            if (f) { f.focus(); }
          });
          res.appendChild(b);
        });
    });
    // pan by dragging the background, zoom with the wheel, keys on the canvas
    var drag = null;
    this.svg.addEventListener("pointerdown", function (e) {
      if (e.target.closest && e.target.closest(".node, .loop-badge, .sector-toggle")) { return; }
      drag = {x: e.clientX, y: e.clientY};
      self.svg.setPointerCapture(e.pointerId);
    });
    this.svg.addEventListener("pointermove", function (e) {
      if (!drag) { return; }
      var s = self.view.w / (self.canvas.clientWidth || 800);
      self.pan(-(e.clientX - drag.x) * s, -(e.clientY - drag.y) * s);
      drag = {x: e.clientX, y: e.clientY};
    });
    this.svg.addEventListener("pointerup", function () { drag = null; });
    this.svg.addEventListener("wheel", function (e) {
      e.preventDefault();
      var r = self.svg.getBoundingClientRect(), v = self.view;
      self.zoom(e.deltaY < 0 ? 1.15 : 1 / 1.15, v.x + (e.clientX - r.left) / r.width * v.w, v.y + (e.clientY - r.top) / r.height * v.h);
    }, {passive: false});
    this.mini.addEventListener("click", function (e) {
      var r = self.mini.getBoundingClientRect(), b = self.bounds;
      self.center(b.x + (e.clientX - r.left) / r.width * b.w, b.y + (e.clientY - r.top) / r.height * b.h);
    });
    this.canvas.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { self.clear(); return; }
      if (e.target !== self.canvas) { return; }
      var step = self.view.w * 0.1;
      var map = {ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step]};
      if (map[e.key]) { e.preventDefault(); self.pan(map[e.key][0], map[e.key][1]); }
      else if (e.key === "+" || e.key === "=") { self.zoom(1.4); }
      else if (e.key === "-") { self.zoom(1 / 1.4); }
      else if (e.key === "0") { self.fit(); }
    });
    this.detailEmpty();
  };
  Structure.prototype.setMode = function (m) {
    this.mode = m;
    document.getElementById("mode-sfd").setAttribute("aria-pressed", String(m === "sfd"));
    document.getElementById("mode-cld").setAttribute("aria-pressed", String(m === "cld"));
    this.fit();
  };

  Structure.prototype.buildLoopList = function () {
    var self = this, ul = document.getElementById("loop-list");
    ul.textContent = "";
    this.S.loops.slice().sort(function (a, b) { return a.name.localeCompare(b.name, undefined, {numeric: true}); }).forEach(function (lp) {
      var li = h("li", "loop-item"), b = h("button", "loop-btn " + (lp.polarity === "R" ? "r" : "b"));
      b.type = "button";
      b.setAttribute("aria-pressed", "false");
      b.appendChild(h("span", "loop-glyph", lp.polarity));
      b.appendChild(h("span", "loop-name", lp.name));
      b.appendChild(h("span", "loop-n", lp.nodes.length + " variables"));
      b.addEventListener("click", function () { self.isolate(lp); });
      lp._btn = b;
      li.appendChild(b);
      ul.appendChild(li);
    });
  };
  Structure.prototype.syncLoopList = function () {
    var self = this, sub = this.run && this.D.ltm ? this.ltmSubset() : null;
    this.S.loops.forEach(function (lp, i) {
      if (!lp._btn) { return; }
      lp._btn.setAttribute("aria-pressed", String(self.loop === lp));
      var tag = lp._btn.querySelector(".loop-out"), out = sub && sub.indexOf(i) < 0;
      if (out && !tag) { lp._btn.appendChild(h("span", "loop-out", "not in this view")); }
      if (!out && tag) { tag.parentNode.removeChild(tag); }
    });
  };

  Structure.prototype.buildLegend = function () {
    var ul = document.getElementById("structure-legend");
    ul.textContent = "";
    function item(draw, text) {
      var li = h("li"), s = el("svg", {viewBox: "0 0 44 24", "aria-hidden": "true", focusable: "false"}, li);
      draw(s);
      li.appendChild(h("span", null, text));
      ul.appendChild(li);
    }
    item(function (s) { el("rect", {"class": "tank", x: 4, y: 3, width: 36, height: 18, rx: 4}, s); el("rect", {"class": "tank-fill", x: 5, y: 12, width: 34, height: 8, rx: 3}, s); },
      "Stock (tank): accumulates its inflows minus its outflows; the fill shows its level at the time shown, as a share of the larger peak of the current and baseline runs");
    item(function (s) { el("rect", {"class": "tank", x: 4, y: 3, width: 36, height: 18, rx: 4}, s); el("line", {"class": "tank-ghost", x1: 6, y1: 10, x2: 38, y2: 10}, s); },
      "Dashed line in a tank: the baseline's level at the same time (ghost)");
    item(function (s) {
      el("path", {"class": "pipe-outer", d: "M2,7 L42,7", style: "stroke-width:4px"}, s);
      el("path", {"class": "pipe-outer", d: "M2,18 L42,18", style: "stroke-width:10px"}, s);
    }, "Pipe width: proportional to the flow at the time shown, compared within one unit; moving dashes travel at a speed proportional to the flow (still under reduced motion, where the values are shown as numbers)");
    item(function (s) {
      el("path", {"class": "pipe-flow chg-up still", d: "M2,7 L42,7", style: "stroke-width:4px;stroke-dasharray:none"}, s);
      el("path", {"class": "pipe-flow chg-down still", d: "M2,18 L42,18", style: "stroke-width:4px;stroke-dasharray:none"}, s);
    }, "One pipe, one colour. Every pipe carries a single flow and is coloured by that flow alone: blue with ▲ when the " +
      "flow is higher than the baseline at the time shown, orange with ▼ when it is lower, grey when it is the same. A " +
      "pipe never mixes the two colours, so blue and orange side by side are two different flows: where pipes share a " +
      "corridor or the outer gutter they run in separate lanes, never on top of each other. Hover or focus a pipe for its " +
      "name and values");
    item(function (s) { el("circle", {"class": "aux", cx: 22, cy: 12, r: 7, style: "stroke:var(--accent);stroke-dasharray:4 2"}, s); },
      "Dashed blue outline: this variable's run differs from the baseline at some time");
    item(function (s) {
      el("path", {"class": "link", d: "M2,7 L40,7", style: "stroke-width:0.8px;stroke-opacity:0.3"}, s);
      el("path", {"class": "link", d: "M2,17 L40,17", style: "stroke-width:4px"}, s);
    }, "Link width and opacity: the link's strength (loops-that-matter link score) at the time shown, relative to the strongest link in the model then; the tooltip gives the score");
    item(function (s) {
      var g = el("g", {"class": "loop-badge r", transform: "translate(22,8) scale(0.5)"}, s);
      el("circle", {r: 17, "class": "badge-bg"}, g);
      el("rect", {"class": "meter-bg", x: -18, y: 21, width: 36, height: 5}, g);
      el("rect", {"class": "meter", x: -18, y: 21, width: 22, height: 5}, g);
    }, "Bar under a loop badge: the loop's share among the loops shown in the Loop strength tab (all loops, or the selected set) at the time shown");
    if (this.D.ltm && this.D.ltm.restrict) {
      item(function (s) {
        var g = el("g", {"class": "loop-badge b outview", transform: "translate(22,12) scale(0.62)"}, s);
        el("circle", {r: 17, "class": "badge-bg"}, g);
        el("text", {y: 4.5, "text-anchor": "middle", "class": "badge-text"}, g).textContent = "B";
      }, "Faded badge with no bar: the loop is not in this view (outside the selected set); it has no share here, which is not the same as a zero share");
    }
    item(function (s) { el("circle", {"class": "ripple-ring", cx: 22, cy: 12, r: 9, style: "opacity:0.8"}, s); },
      "Ring pulse: the effect of a lever you just moved, spreading along the links one step at a time");
    item(function (s) { el("path", {"class": "pipe-outer", d: "M2,12 L42,12"}, s); el("path", {"class": "pipe-inner", d: "M2,12 L42,12"}, s); el("path", {"class": "valve", d: "M14,6 L30,18 L30,6 L14,18 Z"}, s); },
      "Flow (pipe with valve): moves material into or out of stocks per unit of time");
    item(function (s) { el("path", {"class": "cloud-shape", d: "M8,16 a6,6 0 0 1 2,-10 a8,8 0 0 1 14,-2 a6,6 0 0 1 10,5 a5,5 0 0 1 -2,9 z"}, s); },
      "Cloud: a source or sink outside the model boundary");
    item(function (s) { el("circle", {"class": "aux", cx: 22, cy: 12, r: 6}, s); }, "Auxiliary (circle): computed from other variables");
    item(function (s) { el("circle", {"class": "aux exo", cx: 22, cy: 12, r: 6}, s); }, "Exogenous input (grey circle, grey name): a parameter or constant set from outside the model");
    [["+", "Positive link (+, solid): more of the cause gives more of the effect, all else equal"],
      ["-", "Negative link (−, dashed): more of the cause gives less of the effect"],
      ["+/-", "Link of both directions (±, dash-dot): its sign changes during the run"],
      ["0", "Inactive link (0, dotted grey): no effect at the base settings (a switch threshold or a floor that does not bind)"]].forEach(function (p) {
      item(function (s) {
        el("path", {"class": "link" + (p[0] === "0" ? " inactive" : ""), d: "M2,14 L36,14", "stroke-dasharray": DASH[p[0]], "marker-end": "url(#sd-arrow)"}, s);
        var t = el("text", {"class": "sign", x: 22, y: 9, "text-anchor": "middle"}, s);
        t.textContent = GLYPH[p[0]];
      }, p[1]);
    });
    item(function (s) {
      el("path", {"class": "link", d: "M2,12 L42,12"}, s);
      var g = el("g", {"class": "delay-mark"}, s);
      el("line", {x1: 19, y1: 4, x2: 19, y2: 20}, g);
      el("line", {x1: 25, y1: 4, x2: 25, y2: 20}, g);
    }, "Delay (double bar): the cause acts through a delay; hover or focus for its order and time constant from the delay audit");
    item(function (s) {
      var g = el("g", {"class": "loop-badge r", transform: "translate(22,12) scale(0.62)"}, s);
      el("circle", {r: 17, "class": "badge-bg"}, g);
      el("text", {y: 4.5, "text-anchor": "middle", "class": "badge-text"}, g).textContent = "R";
    }, "Reinforcing loop badge (R, solid outline, blue): select it to isolate the loop");
    item(function (s) {
      var g = el("g", {"class": "loop-badge b", transform: "translate(22,12) scale(0.62)"}, s);
      el("circle", {r: 17, "class": "badge-bg"}, g);
      el("text", {y: 4.5, "text-anchor": "middle", "class": "badge-text"}, g).textContent = "B";
    }, "Balancing loop badge (B, dashed outline, orange): select it to isolate the loop");
    item(function (s) { el("rect", {"class": "region", x: 2, y: 3, width: 40, height: 18, rx: 5}, s); },
      "Sector region: select its title to collapse or expand it");
    item(function (s) { el("circle", {"class": "aux", cx: 12, cy: 12, r: 6}, s); el("circle", {"class": "aux", cx: 32, cy: 12, r: 6, opacity: 0.2}, s); },
      "Focus: the selected chain stays solid; everything else fades");
    var li = h("li", "legend-note");
    li.textContent = "Zoom in to see auxiliaries and inputs, or tick “Show all variables”. Link signs come from the model's own equations on the base run; each link's tooltip says how.";
    ul.appendChild(li);
  };

  // ---------- side panels for the time shown: flows table, Pooling, delays ----------
  Structure.prototype.renderLive = function () {
    if (!this.run) { return; }
    var self = this, S = this.S, run = this.run, base = this.base, t = this.t, fmt = SDFormat.fmt;
    var tu = S.time_unit, when = tu.toLowerCase() + " " + run.time[t];
    document.getElementById("st-time").max = String(run.time.length - 1);
    document.getElementById("st-time").value = String(t);
    document.getElementById("st-time-label").textContent = tu + " " + run.time[t];
    // flows table
    var tb = document.getElementById("flows-table");
    tb.textContent = "";
    tb.appendChild(h("caption", "sr-only", "Every flow at " + when + ", current run and " + this.hooks.baselineLabel()));
    var thead = h("thead"), tr = h("tr");
    ["Flow", "From → to", "Current", this.hooks.baselineLabel(), "Change", "Unit"].forEach(function (c) { tr.appendChild(h("th", null, c)); });
    thead.appendChild(tr);
    tb.appendChild(thead);
    var body = h("tbody");
    S.pipes.forEach(function (p) {
      var n = self.byId[p.flow], c = run.series[n.name][t], b = base.series[n.name][t], r = h("tr"), sg = changeSign(c, b);
      r.setAttribute("data-flow-name", n.name);
      var ends = function (ids) { return ids.length ? ids.map(function (x) { return self.byId[x].name; }).join(", ") : "outside"; };
      [n.name, ends(p.from) + " → " + ends(p.to),
        fmt(c), fmt(b), sg === "0" ? "same" : (sg === "+" ? "▲ +" : "▼ ") + fmt(c - b), n.unit].forEach(function (x) { r.appendChild(h("td", null, x)); });
      body.appendChild(r);
    });
    tb.appendChild(body);
    this.renderPooling();
    this.renderDelays();
    this.renderDominance();
  };
  Structure.prototype.thresholds = function () {
    var d = SDPooling.defaults(), g = function (id, f) { var e = document.getElementById(id); return e ? f(Number(e.value)) : null; };
    var self = function (v) { return v; }, bind = g("th-bind", self), build = g("th-build", function (v) { return v / 100; }),
        win = g("th-window", self);                 // 0 is a value the fields accept: only a missing field takes the default
    return {bind: bind === null ? d.bind : bind, build: build === null ? d.build : build,
      window: win === null ? d.window : win};
  };
  // growth in words; from (near) zero a percentage is meaningless, so the two levels are given instead
  function growthText(f, t) {
    var a = f.from[t], b = f.to[t];
    if (Math.abs(a) <= 1e-9 * Math.max(Math.abs(b), 1)) { return "went from " + SDFormat.fmt(a) + " to " + SDFormat.fmt(b); }
    return (b >= a ? "rose " : "fell ") + SDFormat.fmt(Math.abs(f.growth[t]) * 100) + "% (from " + SDFormat.fmt(a) + " to " + SDFormat.fmt(b) + ")";
  }
  Structure.prototype.renderPooling = function () {
    var self = this, S = this.S, run = this.run, base = this.base, t = this.t, fmt = SDFormat.fmt;
    var root = document.getElementById("pool-body"), when = S.time_unit.toLowerCase() + " " + run.time[t];
    var th = document.getElementById("th-bind") ? this.thresholds() : SDPooling.defaults();
    root.textContent = "";
    root.appendChild(h("p", "delay-note", "Every figure below is read from the current run at " + when + "."));
    if (S.pooling.capped.length) {
      var box = h("div", "pool-th");
      [["th-bind", "Binding when demand / capacity ≥", th.bind.toFixed(2), "0.05"],
        ["th-build", "Building up when the stock rose by ≥ (%)", (th.build * 100).toFixed(1), "0.5"],
        ["th-window", "over the last (" + S.time_unit.toLowerCase() + "s)", String(th.window), "1"]].forEach(function (x) {
        var lab = h("label", null, x[1]);
        lab.htmlFor = x[0];
        var inp = h("input");
        inp.type = "number"; inp.id = x[0]; inp.value = x[2]; inp.step = x[3]; inp.min = "0";
        inp.addEventListener("change", function () { self.renderPooling(); });
        box.appendChild(lab);
        box.appendChild(inp);
      });
      root.appendChild(box);
      SDPooling.compute(run, base, th).forEach(function (f, j) {
        var c = S.pooling.capped[j], flow = c.outflow_names.join(" and ");
        var tu = S.time_unit.toLowerCase(), ratioTxt = "demand / capacity " + fmt(f.ratio[t]);
        var close = "the pipeline would close " + fmt(f.demand[t]) + " a " + tu + ", capacity allows " + fmt(f.capacity[t]);
        var grow = isFinite(f.growth[t]) ? c.stock_name + " " + growthText(f, t) + " over the last " + th.window + " " + tu + "s" :
          "too early to measure " + c.stock_name + "'s rise over " + th.window + " " + tu + "s";
        // three states: pooling (binding and building up), binding but not yet building up, and not binding
        var state = f.flagged[t] ? "on" : f.binding_only[t] ? "watch" : "clear", msg;
        if (state === "on") {
          msg = "⚠ Pooling at " + when + ": " + c.cap_name + " limits " + flow + "; " + close + " (" + ratioTxt + " ≥ " + th.bind.toFixed(2) +
            "), and " + grow + " (≥ " + (th.build * 100).toFixed(1) + "%).";
        } else if (state === "watch") {
          msg = "⚠ Capacity binding, not yet building up, at " + when + ": " + c.cap_name + " limits " + flow + "; " + close + " (" + ratioTxt +
            " ≥ " + th.bind.toFixed(2) + "). The excess waits in " + c.stock_name + ", but " + grow + " (below the " + (th.build * 100).toFixed(1) +
            "% build-up threshold). The limit is active now.";
        } else {
          msg = "No binding capacity at " + when + ": " + ratioTxt + " for " + flow + " (< " + th.bind.toFixed(2) + "); " + grow + ".";
        }
        var p = h("p", "pool-flag" + (state === "clear" ? "" : " " + state), msg);
        p.id = j === 0 ? "pool-flag" : "pool-flag-" + j;
        root.appendChild(p);
      });
    } else {
      var p0 = h("p", "pool-flag", "This model has no capacity-capped flow (delay audit), so no pooling flag applies.");
      p0.id = "pool-flag";
      root.appendChild(p0);
    }
    root.appendChild(h("h4", null, "Share of the conserved total"));
    var ol = h("ol");
    ol.id = "pool-shares";
    S.pooling.groups.forEach(function (g) {
      var tot = g.stocks.reduce(function (a, s) { return a + run.series[self.byId[s].name][t]; }, 0);
      g.stocks.map(function (s) { return {name: self.byId[s].name, v: run.series[self.byId[s].name][t]}; })
        .sort(function (a, b) { return b.v - a.v; })
        .forEach(function (x) { ol.appendChild(h("li", null, x.name + ": " + fmt(tot ? x.v / tot * 100 : NaN) + "% of " + g.name)); });
    });
    root.appendChild(ol);
    root.appendChild(h("h4", null, "Level versus " + this.hooks.baselineLabel()));
    var ol2 = h("ol");
    ol2.id = "pool-levels";
    Object.keys(S.nodes).map(function (k) { return S.nodes[k]; }).filter(function (n) { return n.kind === "stock"; })
      .map(function (n) { var c = run.series[n.name][t], b = base.series[n.name][t]; return {name: n.name, rel: b !== 0 ? (c - b) / Math.abs(b) : NaN, sg: changeSign(c, b)}; })
      .sort(function (a, b) { return (isFinite(b.rel) ? Math.abs(b.rel) : -1) - (isFinite(a.rel) ? Math.abs(a.rel) : -1); })
      .forEach(function (x) {
        ol2.appendChild(h("li", null, x.name + ": " + (x.sg === "0" ? "same" : !isFinite(x.rel) ? "baseline is 0" :
          (x.sg === "+" ? "▲ +" : "▼ ") + fmt(x.rel * 100) + "%")));
      });
    root.appendChild(ol2);
  };
  Structure.prototype.renderDominance = function () {
    var self = this, S = this.S, L = this.D.ltm, res = this.ltmResult(), j = this.ltmIndex(), root = document.getElementById("dom-body");
    var fmt = SDFormat.fmt, tu = S.time_unit, names = S.loops.map(function (lp) { return lp.name; }), sub = this.ltmSubset();
    root.textContent = "";
    var g = L.gate;
    var statement = L.mode === "live" ?
      "Live for the current levers: loops-that-matter link and loop scores for this run. Method as implemented in " +
      "engine/loop_detector.py, reimplemented there from the published definition and not checked against the paper; " +
      "this page's JavaScript matches loop_detector on " + g.runs + " lever settings (" + g.link_series + " link series, " +
      g.loop_series + " loop series): largest scale-normalised difference " + g.end_to_end_link.toExponential(1) + " for links and " +
      g.end_to_end_loop.toExponential(1) + " for loops (tolerance " + g.tolerance + ")." :
      "Precomputed for the base case only (engine/loop_detector.py on the PySD base run): these values do not follow the " +
      "levers. Reason: " + L.reason + ". Method reimplemented in loop_detector from the published definition and not " +
      "checked against the paper.";
    root.appendChild(h("p", "dom-mode", L.mode === "live" ? "Live for the current levers; follows the time shown." :
      "Precomputed for the base case only: these values do not follow the levers."));
    if (L.restrict) {
      // radio buttons, not a select: labels wrap instead of being cut off at any width
      var fs = h("fieldset", "dom-restrict");
      fs.appendChild(h("legend", null, "Loops shown"));
      var nAll = S.loops.length, nSub = S.loops.filter(function (lp) {
        return lp.nodes.some(function (n) { return S.nodes[n].name === L.restrict.stock; });
      }).length;
      [["on", "Through " + L.restrict.stock + ": " + nSub + " loops (" + L.restrict.label + ", as gate 8)"],
        ["off", "All " + nAll + " loops (model-wide)"]].forEach(function (o) {
        var lab = h("label", "dom-opt"), inp = h("input");
        inp.type = "radio";
        inp.name = "dom-restrict";
        inp.value = o[0];
        inp.checked = (self.restrictOn !== false) === (o[0] === "on");
        inp.addEventListener("change", function () {
          if (!inp.checked) { return; }
          self.restrictOn = o[0] === "on";
          self.render();
          var back = document.querySelector("input[name=dom-restrict][value=" + o[0] + "]");
          if (back) { back.focus(); }
        });
        lab.appendChild(inp);
        lab.appendChild(h("span", null, o[1]));
        fs.appendChild(lab);
      });
      root.appendChild(fs);
      if (this.restrictOn !== false) {
        root.appendChild(h("p", "delay-note", L.restrict.label.charAt(0).toUpperCase() + L.restrict.label.slice(1) + ": the same scores renormalised over the " + sub.length +
          " loops through " + L.restrict.stock + ", as recorded in " + L.restrict.source + ". The model-wide ranking names a side loop. " +
          "Loops outside this set are marked “not in this view” on the diagram and in the Loops list."));
      }
    }
    // method statement, collapsed under the timeline; shown whether or not there is a chart above it
    var showMethod = function () {
      var md = h("details", "dom-method");
      md.id = "dom-method";
      md.open = !!self.methodOpen;
      md.addEventListener("toggle", function () { self.methodOpen = md.open; });
      md.appendChild(h("summary", null, "Method and check against loop_detector"));
      md.appendChild(h("p", "delay-note", statement));
      root.appendChild(md);
    };
    // stacked shares over time (each loop's |relative score| renormalised over the loops shown)
    var T = res.time, W = 260, H = 110, n = T.length;
    var mean = sub.map(function (i) {
      var s0 = 0, c = 0;
      for (var k = 0; k < n; k++) { var v = res.rel[i][k]; if (isFinite(v)) { s0 += Math.abs(v); c++; } }
      return {i: i, m: c ? s0 / c : 0};
    }).sort(function (a, b) { return b.m - a.m; });
    var floor = new Array(n).fill(0), tot = new Array(n).fill(0);
    for (var k = 0; k < n; k++) { sub.forEach(function (i) { var v = res.rel[i][k]; if (isFinite(v)) { tot[k] += Math.abs(v); } }); }
    // Where no loop carries a score, every relative score at that step is NaN and a band drawn for it has zero
    // height. With no step scored there is nothing to draw at all: say so, because an empty chart cannot be told
    // apart from a broken one (projects/car-dealership-profit freezes a link in all 67 of its loops at base).
    var scored = 0;
    for (var kc = 0; kc < n; kc++) { if (tot[kc] > 0) { scored++; } }
    if (!scored) {
      root.appendChild(h("p", "dom-empty", "No loop strength to show at these lever settings: no loop carries a score "
        + "at any of the " + n + " time steps" + (L.empty_at_base ? ", because " + L.empty_at_base : "") + "."));
      showMethod();
      return;
    }
    if (scored < n) {
      root.appendChild(h("p", "dom-empty", (n - scored) + " of the " + n + " time steps carry no loop score and are "
        + "drawn empty: no loop changes anything there."));
    }
    var svg = el("svg", {viewBox: "0 0 " + W + " " + (H + 18), "class": "dom-chart", role: "img",
      "aria-label": "Share of loop strength over time, stacked; details in the list below"}, root);
    var X = function (t) { return 4 + (t - T[0]) / ((T[n - 1] - T[0]) || 1) * (W - 8); };
    var rankR = 0, rankB = 0, step = Math.max(1, Math.floor(n / 240));
    mean.forEach(function (o) {
      var lp = S.loops[o.i], isR = lp.polarity === "R", rank = isR ? rankR++ : rankB++;
      var top = [], d = "";
      for (var k = 0; k < n; k += step) {
        var v = res.rel[o.i][k], sh = tot[k] > 0 && isFinite(v) ? Math.abs(v) / tot[k] : 0;
        top.push([X(T[k]), H - (floor[k] + sh) * H]);
      }
      var bottom = [];
      for (var k2 = 0; k2 < n; k2 += step) { bottom.push([X(T[k2]), H - floor[k2] * H]); }
      for (var k3 = 0; k3 < n; k3 += step) {
        var v3 = res.rel[o.i][k3];
        floor[k3] += tot[k3] > 0 && isFinite(v3) ? Math.abs(v3) / tot[k3] : 0;
      }
      d = "M" + top.map(function (q) { return q[0].toFixed(1) + "," + q[1].toFixed(1); }).join("L") + "L" +
        bottom.reverse().map(function (q) { return q[0].toFixed(1) + "," + q[1].toFixed(1); }).join("L") + "Z";
      var path = el("path", {d: d, "class": "dom-band " + (isR ? "r" : "b"), "data-loop-name": lp.name,
        style: "fill-opacity:" + Math.max(0.18, 0.85 - 0.16 * rank).toFixed(2)}, svg);
      el("title", {}, path).textContent = lp.name + " (" + (isR ? "reinforcing" : "balancing") + ")";
      path.addEventListener("click", function () { self.isolate(lp); });
    });
    if (j >= 0) { el("line", {"class": "dom-now", x1: X(T[j]), x2: X(T[j]), y1: 0, y2: H}, svg); }
    el("text", {x: 4, y: H + 14}, svg).textContent = tu + " " + T[0];
    el("text", {x: W - 4, y: H + 14, "text-anchor": "end"}, svg).textContent = tu + " " + T[n - 1];
    // strongest loops at the time shown
    if (j >= 0) {
      root.appendChild(h("h4", null, "Strongest at " + tu.toLowerCase() + " " + T[j]));
      var ol = h("ol");
      ol.id = "dom-now";
      sub.map(function (i) { return {i: i, v: res.rel[i][j]}; }).filter(function (o) { return isFinite(o.v); })
        .map(function (o) { return {i: o.i, sh: tot[j] > 0 ? Math.abs(o.v) / tot[j] : 0}; })
        .sort(function (a, b) { return b.sh - a.sh; }).slice(0, 5)
        .forEach(function (o) { ol.appendChild(h("li", null, names[o.i] + ": " + fmt(o.sh * 100) + "%")); });
      root.appendChild(ol);
    }
    // dominance periods (shorter than one time unit folded into the previous one)
    root.appendChild(h("h4", null, "Dominant loop by period"));
    var ol2 = h("ol");
    ol2.id = "dom-periods";
    SDLtm.dominance(res.rel, T, sub, names, 1.0).forEach(function (p) {
      var li = h("li", null, tu + "s " + fmt(p.start) + "–" + fmt(p.end) + ": " + p.loop);
      li.setAttribute("data-start", p.start);
      li.setAttribute("data-end", p.end);
      li.setAttribute("data-loop", p.loop);
      ol2.appendChild(li);
    });
    root.appendChild(ol2);
    showMethod();
  };
  Structure.prototype.renderDelays = function () {
    var S = this.S, ul = document.getElementById("delay-list");
    if (ul.childNodes.length) { return; }
    S.delays.forEach(function (d) {
      var li = h("li");
      li.setAttribute("data-stock", d.stock);
      li.setAttribute("data-order", d.order);
      li.setAttribute("data-tau", d.tau);
      li.appendChild(h("strong", null, d.stock));
      li.appendChild(h("div", null, (d.order === 1 ? "First-order " : "Order " + d.order + " ") + d.type + " delay (" + d.order +
        " stock" + (d.order === 1 ? "" : "s") + "), τ = " + d.tau + " = " + SDFormat.fmt(d.tau_base) + " " + S.time_unit + " at t = 0"));
      // step response of an order-n delay (Erlang): 1 - e^(-n t / tau) sum_{k<n} (n t / tau)^k / k!
      var sv = el("svg", {viewBox: "0 0 240 70", role: "img", "aria-label": "Step response of the delay over 0 to 4 tau"}, li), pts = [];
      for (var i = 0; i <= 80; i++) {
        var x = i / 20, nt = d.order * x, sum = 0, term = 1;
        for (var k = 0; k < d.order; k++) { if (k > 0) { term *= nt / k; } sum += term; }
        pts.push((20 + x * 52).toFixed(1) + "," + (58 - (1 - Math.exp(-nt) * sum) * 48).toFixed(1));
      }
      el("line", {"class": "axis", x1: 20, y1: 58, x2: 230, y2: 58}, sv);
      el("line", {"class": "axis", x1: 20, y1: 10, x2: 20, y2: 58}, sv);
      el("path", {"class": "response", d: "M" + pts.join("L")}, sv);
      ["0", "τ", "2τ", "3τ", "4τ"].forEach(function (lab, j) { el("text", {x: 20 + j * 52, y: 68, "text-anchor": "middle"}, sv).textContent = lab; });
      el("text", {x: 16, y: 13, "text-anchor": "end"}, sv).textContent = "1";
      li.appendChild(h("p", "delay-note", "Step response: ideal continuous-time reference; the model uses Euler with dt = " +
        S.time_step + " " + S.time_unit + "."));
      ul.appendChild(li);
    });
  };

  return {Structure: Structure};
})();
