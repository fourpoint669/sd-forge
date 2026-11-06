// Link and loop scores for the run on the page, ported operation by operation from engine/loop_detector.py
// (link_scores, analyze). Method: loops that matter (Schoenberg, Davidsen and Eberlein, System Dynamics Review 2020),
// reimplemented in loop_detector.py from the published definition; it has not been checked against the paper.
//   link score  LS(x->z) = |D_x z / D z| * sign(D_x z / D x)            (0 when D z or D x is within 1e-9 of scale)
//   loop score  = product of its link scores; relative = loop score / sum over loops of |loop score|
var SDLtm = (function () {
  "use strict";
  var REL_TOL = 1e-9;
  function nanToNum(x) {
    if (x !== x) { return 0; }
    if (x === Infinity) { return Number.MAX_VALUE; }
    if (x === -Infinity) { return -Number.MAX_VALUE; }
    return x;
  }
  function scale(a) {
    var m = -Infinity;
    for (var i = 0; i < a.length; i++) { var v = Math.abs(a[i]); if (v > m) { m = v; } }
    return Math.max(m, 1e-300);
  }
  // series: {real name: values on the saved grid}; time: saved times; names: {py: real}; eqs/meta from SDEqs/SDEQ_META
  function linkScores(series, time, names, eqs, meta) {
    var T = time.length, V = [], py = Object.keys(names), links = {};
    for (var k = 0; k < T; k++) {
      var o = {time: time[k]};
      for (var j = 0; j < py.length; j++) { o[py[j]] = series[names[py[j]]][k]; }
      V.push(o);
    }
    Object.keys(meta).sort().forEach(function (z) {
      var deps = meta[z], f = eqs[z];
      if (!deps.length) { return; }
      if (!f) { deps.forEach(function (x) { links[x + ">" + z] = null; }); return; }
      var full = new Array(T);
      for (var k2 = 0; k2 < T; k2++) { full[k2] = f(V[k2]); }
      var sz = scale(full), dz = new Array(T - 1), dzOk = new Array(T - 1);
      for (var k3 = 0; k3 < T - 1; k3++) { dz[k3] = full[k3 + 1] - full[k3]; dzOk[k3] = Math.abs(dz[k3]) > REL_TOL * sz; }
      deps.forEach(function (x) {
        var xa = x === "time" ? time : series[names[x]], sx = scale(xa), out = new Array(T - 1);
        for (var k4 = 0; k4 < T - 1; k4++) {
          var dx = xa[k4 + 1] - xa[k4], okx = Math.abs(dx) > REL_TOL * sx, keep = V[k4][x];
          V[k4][x] = xa[k4 + 1];
          var dxz = f(V[k4]) - full[k4];
          V[k4][x] = keep;
          out[k4] = nanToNum(dzOk[k4] && okx ? Math.abs(dxz / dz[k4]) * Math.sign(dxz / dx) : 0);
        }
        links[x + ">" + z] = out;
      });
    });
    return links;
  }
  // loops: arrays of py names in cycle order; returns {score: [...], rel: [...]} per loop, on time[1:]
  function loopScores(links, loops, n) {
    var S = loops.map(function (lp) {
      var edges = lp.map(function (a, i) { return a + ">" + lp[(i + 1) % lp.length]; });
      var arrs = edges.map(function (e) { return links[e]; });
      var scored = arrs.every(function (a) { return a !== null && a !== undefined; });
      var s = new Array(n);
      for (var k = 0; k < n; k++) {
        if (!scored) { s[k] = NaN; continue; }
        var p = 1;
        for (var j = 0; j < arrs.length; j++) { p *= arrs[j][k]; }
        s[k] = p;
      }
      return s;
    });
    var rel = S.map(function () { return new Array(n); });
    for (var k = 0; k < n; k++) {
      var tot = 0;
      for (var i = 0; i < S.length; i++) { if (S[i][k] === S[i][k]) { tot += Math.abs(S[i][k]); } }
      for (var i2 = 0; i2 < S.length; i2++) { rel[i2][k] = tot > 0 ? S[i2][k] / tot : NaN; }
    }
    return {score: S, rel: rel};
  }
  // dominance over a subset of loops (renormalised over that subset), periods shorter than minLength folded into the
  // previous one, as gate8_analysis.py does for the customer-restricted view
  function dominance(rel, time, subset, labels, minLength) {
    var periods = [], dom = [];
    for (var c = 0; c < time.length; c++) {
      var tot = 0, any = false;
      subset.forEach(function (i) { var v = rel[i][c]; if (v === v) { tot += Math.abs(v); any = true; } });
      var best = null, bv = -1;
      if (any) {
        subset.forEach(function (i, j) {
          var v = rel[i][c] / tot;
          if (v === v && Math.abs(v) > bv) { bv = Math.abs(v); best = j; }
        });
      }
      dom.push(best);
    }
    var start = 0;
    for (var c2 = 1; c2 <= dom.length; c2++) {
      if (c2 === dom.length || dom[c2] !== dom[start]) {
        if (dom[start] !== null) { periods.push({start: time[start], end: time[c2 - 1], loop: labels[subset[dom[start]]]}); }
        start = c2;
      }
    }
    var merged = [];
    periods.forEach(function (p) {
      var last = merged[merged.length - 1];
      if (last && (p.end - p.start < minLength || p.loop === last.loop)) { last.end = p.end; } else { merged.push(p); }
    });
    return merged;
  }
  function compute(run, eqs, meta, names, loops) {
    var links = linkScores(run.series, run.time, names, eqs, meta);
    var L = loopScores(links, loops, run.time.length - 1);
    return {time: run.time.slice(1), links: links, score: L.score, rel: L.rel};
  }
  return {compute: compute, linkScores: linkScores, loopScores: loopScores, dominance: dominance};
})();
