// Runs the page's link/loop-score code under node for the LTM gate (engine/explorer_ltm.py).
// stdin: {"engine", "eqs", "ltm": script texts, "names": {py: real}, "loops": [[py...]], "dt": number,
//         "runs": [{"params": {...}} | {"values": {"time": [...], "series": {real: [...]}}}], "restrict": [...]?}
// stdout: [{"time": [...], "links": {"x>z": [...] | null}, "rel": [[...]]}] with non-finite numbers as strings.
"use strict";
const vm = require("vm");

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (c) => { input += c; });
process.stdin.on("end", () => {
  const job = JSON.parse(input);
  const ctx = vm.createContext({});
  vm.runInContext(job.engine, ctx, { filename: "sd-engine.js" });
  vm.runInContext(job.eqs, ctx, { filename: "sd-eqs.js" });
  vm.runInContext(job.ltm, ctx, { filename: "sd-ltm.js" });
  const SDEngine = vm.runInContext("SDEngine", ctx), SDLtm = vm.runInContext("SDLtm", ctx);
  const eqs = vm.runInContext("SDEqs", ctx), meta = vm.runInContext("SDEQ_META", ctx);
  const dec = (a) => a.map((x) => (typeof x === "string" ? Number(x) : x));
  const enc = (x) => (Number.isFinite(x) ? x : String(x));
  const out = job.runs.map((r) => {
    let run;
    if (r.values) {
      const series = {};
      Object.keys(r.values.series).forEach((k) => { series[k] = dec(r.values.series[k]); });
      run = { time: dec(r.values.time), series };
    } else {
      run = SDEngine.run(r.params || {}, { saveper: job.dt });
    }
    const res = SDLtm.compute(run, eqs, meta, job.names, job.loops);
    const links = {};
    Object.keys(res.links).forEach((k) => { links[k] = res.links[k] === null ? null : res.links[k].map(enc); });
    const row = { time: res.time.map(enc), links, rel: res.rel.map((a) => a.map(enc)) };
    if (job.restrict) { row.dominance = SDLtm.dominance(res.rel, res.time, job.restrict.subset, job.restrict.labels, job.restrict.min_length); }
    return row;
  });
  process.stdout.write(JSON.stringify(out));
});
