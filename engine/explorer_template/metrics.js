// Headline metrics, mirroring engine/validate.py stat() (value_at = np.interp; time_of_max = first maximum;
// time_to_reach = first time series >= value, else Infinity). The parity gate runs this exact text under node.
var SDMetrics = (function () {
  "use strict";
  function interp(x, t, y) {
    var n = t.length;
    if (x <= t[0]) { return y[0]; }
    if (x >= t[n - 1]) { return y[n - 1]; }
    var lo = 0, hi = n - 1;
    while (hi - lo > 1) {
      var mid = (lo + hi) >> 1;
      if (t[mid] <= x) { lo = mid; } else { hi = mid; }
    }
    if (t[lo] === x) { return y[lo]; }
    var slope = (y[lo + 1] - y[lo]) / (t[lo + 1] - t[lo]);
    return slope * (x - t[lo]) + y[lo];
  }
  function stat(t, y, s) {
    var i, best;
    switch (s.stat) {
      case "max": return Math.max.apply(null, y);
      case "min": return Math.min.apply(null, y);
      case "final": return y[y.length - 1];
      case "initial": return y[0];
      case "time_of_max":
        best = 0;
        for (i = 1; i < y.length; i++) { if (y[i] > y[best]) { best = i; } }
        return t[best];
      case "value_at": return interp(s.time, t, y);
      case "time_to_reach":
        for (i = 0; i < y.length; i++) { if (y[i] >= s.value) { return t[i]; } }
        return Infinity;
      default: throw new Error("unknown stat " + s.stat);
    }
  }
  function all(run, defs) {
    var out = {};
    defs.forEach(function (d) { out[d.name] = stat(run.time, run.series[d["var"]], d); });
    return out;
  }
  return {stat: stat, all: all};
})();
