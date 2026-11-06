// Runs an sd-explorer engine script under node for the parity gate (engine/explorer_parity.py).
// stdin: {"engine": "<script text>", "runs": [{"params": {...}, "opts": {...}}],
//         optional "metrics": "<SDMetrics script text>", "metric_defs": [validation.toml montecarlo metrics]}
// stdout: [{"time": [...], "series": {name: [...]}, "metrics": {name: value}}],
//         non-finite numbers encoded as "NaN" / "Infinity" / "-Infinity".
// The script is evaluated in a fresh vm context with no require, process or network access.
"use strict";
const vm = require("vm");

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (c) => { input += c; });
process.stdin.on("end", () => {
  const job = JSON.parse(input);
  const ctx = vm.createContext({});
  vm.runInContext(job.engine, ctx, { filename: "sd-engine.js" });
  const engine = vm.runInContext("SDEngine", ctx);
  let metrics = null;
  if (job.metrics) {
    vm.runInContext(job.metrics, ctx, { filename: "sd-metrics.js" });
    metrics = vm.runInContext("SDMetrics", ctx);
  }
  const enc = (x) => (Number.isFinite(x) ? x : String(x));
  const out = job.runs.map((r) => {
    try {
      const res = engine.run(r.params || {}, r.opts || {});
      const series = {};
      for (const k of Object.keys(res.series)) { series[k] = res.series[k].map(enc); }
      const row = { time: res.time.map(enc), series };
      if (metrics) {
        const m = metrics.all(res, job.metric_defs || []);
        row.metrics = {};
        for (const k of Object.keys(m)) { row.metrics[k] = enc(m[k]); }
      }
      return row;
    } catch (e) {
      return { error: String(e && e.message || e) };
    }
  });
  process.stdout.write(JSON.stringify(out));
});
