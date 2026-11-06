"""Build projects/<model>/explorer.html: one self-contained interactive page that re-runs the validated model.

Usage:  python -I engine/build_explorer.py [--projects-root DIR] <projects/<model> | <model>>
        A bare <model> name is looked up under the projects root (engine/sd_paths.py: --projects-root, SD_PROJECTS_DIR,
        else the current directory).

Steps (any failure stops the build; nothing is written on refusal):
  1. Refuse unless validation_report.md says 'Overall: **PASS**', validation_results.json has all_pass = true and its
     recorded sha256 of validation.toml and of the model .mdl and .py equal the files on disk, and, where the project
     has checks.py, checks_results.json has all_pass = true and its recorded sha256 of every file the checks read
     equal those files now (engine/explorer_release.py). At the end, the sha256 of every project file the page rests
     on (explorer_release.STAMPED that exist, and the model) and of the page template is stamped into the page and
     explorer_parity.json, so check_repo.py can tell when a shipped page no longer matches its project.
  2. Metadata for every variable (engine/explorer_meta.py); missing metadata fails.
  3. Page settings from explorer.toml (generated with defaults if absent; engine/explorer_config.py).
  4. Emit the JS engine (engine/export_js.py) and run the parity gate against PySD (engine/explorer_parity.py),
     including the page's headline-metric code. Fails unless every check is within 1e-9.
  5. Inline template, data, engine and metrics into one HTML; refuse external references; report the size.
Writes explorer.html and explorer_parity.json next to validation.toml. Output is deterministic.
"""
import csv
import hashlib
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import explorer_config  # noqa: E402
import explorer_intake  # noqa: E402
import explorer_meta  # noqa: E402
import explorer_ltm  # noqa: E402
import explorer_parity  # noqa: E402
import explorer_release  # noqa: E402
import explorer_structure  # noqa: E402
import run_mode  # noqa: E402
import sd_paths  # noqa: E402
import export_js  # noqa: E402
import validate  # noqa: E402  (read-only dependency)

TEMPLATE = os.path.join(HERE, "explorer_template")
SIZE_TARGET = explorer_release.SIZE_TARGET
EXTERNAL = explorer_release.EXTERNAL
Refused = explorer_release.Refused
check_release = explorer_release.check_release
PERCENTILES = ("P5", "P25", "P50", "P75", "P95")


def _finite(x):
    """JSON-safe: infinite bounds become None (unbounded)."""
    if isinstance(x, float) and not math.isfinite(x):
        return None
    if isinstance(x, (list, tuple)):
        return [_finite(v) for v in x]
    if isinstance(x, dict):
        return {k: _finite(v) for k, v in x.items()}
    return x


def read_bands(project_dir, spec):
    """Monte Carlo bands, each attached to the one preset it applies to. mc_bands.csv: validate.py's bands for the
    FIRST [[policies]] entry (its baseline for gains); scenario_bands.csv (if present): 'scenario|var|P' columns."""
    out = []
    pols = spec.get("policies") or [{"name": "base"}]
    n = spec.get("montecarlo", {}).get("n")
    seed = spec.get("montecarlo", {}).get("seed")
    label = f"Monte Carlo over all parameter ranges (N = {n}, seed {seed}), P5-P95 and P25-P75"

    def load(path, prefix=None):
        rows = list(csv.DictReader(open(path, encoding="utf-8")))
        series = {}
        for col in rows[0]:
            parts = col.split("|")
            if prefix is not None:
                if len(parts) != 3 or parts[0] != prefix:
                    continue
                parts = parts[1:]
            if len(parts) == 2 and parts[1] in PERCENTILES:
                series.setdefault(parts[0], {})[parts[1]] = [float(r[col]) for r in rows]
        return [float(r["time"]) for r in rows], series

    mc = os.path.join(project_dir, "mc_bands.csv")
    if os.path.exists(mc):
        t, s = load(mc)
        out.append({"preset": pols[0]["name"], "source": "mc_bands.csv", "label": label, "time": t, "series": s})
    sc = os.path.join(project_dir, "scenario_bands.csv")
    if os.path.exists(sc):
        head = next(csv.reader(open(sc, encoding="utf-8")))
        names = sorted({c.split("|")[0] for c in head if c.count("|") == 2})
        for p in pols:
            if p["name"] in names and not any(b["preset"] == p["name"] for b in out):
                t, s = load(sc, p["name"])
                out.append({"preset": p["name"], "source": "scenario_bands.csv", "label": label, "time": t,
                            "series": s})
    return out


def page_data(project_dir, spec, ir, meta, cfg, parity, engine_sha):
    base = validate.base_params(spec)
    sector_of = {v: s for s, vs in spec.get("sectors", {}).items() for v in vs}
    sectors = list(spec.get("sectors", {}))
    levers = []
    for name, v in spec["parameters"].items():
        levers.append({"name": name, "base": v["base"], "low": v["low"], "high": v["high"],
                       "domain": v.get("domain", [-math.inf, math.inf]), "unit": v.get("unit", ""),
                       "fixed": v.get("distribution") == "fixed" or v["low"] == v["high"],
                       "sector": sector_of.get(name, "other")})
    levers.sort(key=lambda l: (sectors.index(l["sector"]) if l["sector"] in sectors else len(sectors)))
    presets = [{"name": p["name"], "params": validate.apply_changes(spec, base, p.get("changes"))}
               for p in spec.get("policies", [])]
    summary = open(os.path.join(project_dir, "summary.md"), encoding="utf-8").read()
    title = re.sub(r"^#\s*(Summary:\s*)?", "", summary.splitlines()[0]).strip()
    m = spec["model"]
    return _finite({
        "project": m["name"], "title": title, "time_unit": m.get("time_unit", "Time"),
        "decision": cfg["decision"], "charts": cfg["charts"],
        "metrics": spec.get("montecarlo", {}).get("metrics", []),
        "levers": levers, "sectors": sectors, "base": base, "presets": presets,
        "variables": meta["variables"], "model_limits": meta["model_limits"],
        "run_mode": {"mode": meta["run_mode"], "label": run_mode.label(meta["run_mode"])},
        "bands": read_bands(project_dir, spec),
        "provenance": {"model_file": m["py"], "model_sha256": ir["sha256"], "engine_sha256": engine_sha,
                       "pysd": "3.14.3", "parity_runs": parity["n_runs"], "parity_random": parity["n_random"],
                       "parity_series": parity["n_series"], "parity_max_scale_rel": parity["max_scale_rel"],
                       "parity_max_pointwise_rel": parity["max_pointwise_rel"],
                       "headline_max_rel": parity["headline"]["max_rel"], "tolerance": explorer_parity.TOL,
                       "validation": "validation_report.md: Overall PASS" + (
                           "; checks_results.json: all_pass" if os.path.exists(
                               os.path.join(project_dir, "checks.py")) else "")},
    })


def _read(name):
    return open(os.path.join(TEMPLATE, name), encoding="utf-8").read()


def assemble(title, data, engine_js, metrics_js, eqs_js):
    blob = export_js.json_for_script(data, sort_keys=True, ensure_ascii=False, allow_nan=False)
    for script in (engine_js, metrics_js, eqs_js, _read("ltm.js"), _read("charts.js"), _read("structure.js"), _read("app.js")):
        if "</script" in script.lower():
            # export_js escapes '<' in everything model-derived, so this is a backstop: a page that could close its
            # own script element is never written.
            raise Refused("generated script text contains '</script': nothing written")
    html = _read("index.html")
    banner = run_mode.banner_html((data.get("run_mode") or {}).get("mode", "full"))
    if banner:                                  # express builds only; no template file changes
        html = html.replace("<body>\n", "<body>\n" + banner, 1)
    for marker, value in (("/*@STYLE@*/", _read("style.css")), ("@TITLE@", _html_escape(title)),
                          ("/*@DATA@*/", blob), ("/*@ENGINE@*/", engine_js), ("/*@METRICS@*/", metrics_js),
                          ("/*@EQS@*/", eqs_js), ("/*@LTM@*/", _read("ltm.js")),
                          ("/*@CHARTS@*/", _read("charts.js")), ("/*@STRUCTURE@*/", _read("structure.js")),
                          ("/*@APP@*/", _read("app.js"))):
        if html.count(marker) != 1:
            raise Refused(f"template marker {marker} must appear exactly once, found {html.count(marker)}: nothing written")
        html = html.replace(marker, value)
    return html


def _html_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def extract_script(html, script_id):
    """Exact text of <script id="script_id" ...>...</script>."""
    m = re.search(r'<script id="' + re.escape(script_id) + r'"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise ValueError(f"no script {script_id}")
    return m.group(1)


def external_refs(html):
    return sorted({m.group(0) for m in EXTERNAL.finditer(html)})


def ltm_data(project_dir, spec, gate, force_precomputed=False):
    """What the page needs for link and loop strength: live (gate passed) or precomputed base-case scores (gate failed,
    or forced for a test), the gate's numbers, the loops in cycle order, and the stock-restricted view when the project
    recorded one (gate8_results.json: dominance_customer_loops_base_run)."""
    mode = "precomputed" if force_precomputed or not gate["pass"] else "live"
    g8 = os.path.join(project_dir, "gate8_results.json")
    restrict = None
    if os.path.exists(g8) and "dominance_customer_loops_base_run" in json.load(open(g8)):
        restrict = {"stock": "Customers", "label": "customer-restricted", "source": "gate8_results.json"}
    out = {"mode": mode, "loops": explorer_ltm.loops_of(project_dir), "restrict": restrict, "dt": spec["model"]["time_step"],
           "gate": {"pass": gate["pass"], "tolerance": gate["tolerance"], "runs": gate["n_runs"],
                    "link_series": gate["n_link_series"], "loop_series": gate["n_loop_series"],
                    "end_to_end_link": gate["end_to_end"]["max_link"], "end_to_end_loop": gate["end_to_end"]["max_loop"],
                    "implementation_link": gate["implementation"]["max_link"],
                    "implementation_loop": gate["implementation"]["max_loop"]},
           "reason": None if mode == "live" else ("forced for a test build" if force_precomputed and gate["pass"] else
                                                  "the JavaScript scores did not match loop_detector within the tolerance"),
           # why this model has no loop strength to show at base, when validation recorded one (T8); the page says
           # this instead of drawing bands of zero height
           "empty_at_base": spec.get("dominance_empty_at_base")}
    if mode == "precomputed":
        out["precomputed"] = explorer_ltm.precomputed(project_dir, spec, spec["model"]["time_step"])   # every dt, as gate 8 used
    return out


def apply_intake(project_dir, spec, cfg):
    """Page settings from explorer_intake.toml (engine/explorer_intake.py), or assumed defaults when there is none.
    A chosen decision metric replaces explorer.toml's (and leads the headline and the outcome chart); an assumed one
    keeps explorer.toml's. Returns what the page needs and the text for its Model limits dialog."""
    s = explorer_intake.load(project_dir)
    dec = cfg["decision"]
    if s["decision"]["source"] == explorer_intake.CHOSEN and s["decision"]["metric"] != dec["metric"]:
        m = s["decision"]["metric"]
        dec["headline"] = [m] + [x for x in dec.get("headline", []) if x != m][:3]
        dec["metric"] = m
        var = {x["name"]: x for x in spec["montecarlo"]["metrics"]}[m]["var"]
        for c in cfg["charts"]:
            if c.get("kind") == "outcome":
                c["vars"], c["title"] = [var], var + " over time"
    else:
        s["decision"]["metric"] = dec["metric"]
    pols = spec.get("policies", [])
    lv = s["levers"]["value"]
    exposed = None
    if lv != "all":
        exposed = {k for p in pols for k in (p.get("changes") or {})}
        if lv == "policy+estimated":
            exposed |= {k for k, v in spec["parameters"].items() if v.get("confidence") == "estimated"}
    return {"exposed": exposed, "baseline": s["decision"]["baseline"],
            "page": {"mode": s["mode"], "audience": s["audience"]["value"], "levers": lv,
                     "settings": explorer_intake.settings_text(s, spec)}}


def build(project_dir, force_ltm_precomputed=False):
    project_dir = os.path.abspath(project_dir)
    explorer_release.check_release(project_dir)             # refuses unless validation (and checks) passed
    spec = validate.load_spec(os.path.join(project_dir, "validation.toml"))
    ir = export_js.load_ir(spec["model"]["py_path"])
    meta = explorer_meta.build_metadata(spec, ir, project_dir)
    cfg = explorer_config.load_config(project_dir, spec, {k: v["kind"] for k, v in meta["variables"].items()})
    intake = apply_intake(project_dir, spec, cfg)
    engine_js = export_js.emit_js(ir)
    metrics_js = _read("metrics.js")
    parity = explorer_parity.run_parity(spec, engine_js, metrics_js=metrics_js)
    engine_sha = hashlib.sha256(engine_js.encode()).hexdigest()
    parity.update(engine_sha256=engine_sha, model_sha256=ir["sha256"],
                  metrics_sha256=hashlib.sha256(metrics_js.encode()).hexdigest(),
                  spec_sha256=hashlib.sha256(open(os.path.join(project_dir, "validation.toml"), "rb").read()).hexdigest())
    if not parity["pass"]:
        raise RuntimeError("parity gate failed: " + json.dumps({k: parity[k] for k in (
            "max_scale_rel", "max_pointwise_rel", "worst_scale", "worst_pointwise", "missing_columns", "errors",
            "headline")}, default=str))
    data = page_data(project_dir, spec, ir, meta, cfg, parity, engine_sha)
    data["structure"] = _finite(explorer_structure.build_structure(project_dir))
    gate = explorer_ltm.run_ltm_gate(spec, project_dir)
    parity["ltm"] = {k: gate[k] for k in ("labels", "n_runs", "n_link_series", "n_loop_series", "end_to_end",
                                          "implementation", "tolerance", "pass", "mode")}
    data["ltm"] = _finite(ltm_data(project_dir, spec, gate, force_ltm_precomputed))
    # stamped after explorer.toml exists (written on a first build), so the stamp covers every project file read
    data["release"] = parity["release"] = explorer_release.release_stamp(project_dir)
    data["intake"], data["baseline_default"] = intake["page"], intake["baseline"]
    exposed = intake["exposed"]
    for l in data["levers"]:
        l["exposed"] = exposed is None or l["name"] in exposed
    eqs_js = export_js.emit_eqs(spec["model"]["py_path"])
    html = assemble(data["title"], data, engine_js, metrics_js, eqs_js)
    if extract_script(html, "sd-engine") != engine_js or extract_script(html, "sd-metrics") != metrics_js:
        raise RuntimeError("inlined scripts differ from the parity-tested scripts")
    refs = external_refs(html)
    if refs:
        raise RuntimeError(f"external references in the page: {refs}")
    size = len(html.encode("utf-8"))
    if size >= SIZE_TARGET:                           # refuse before writing: an over-size page used to be left on disk
        raise Refused(f"page is {size:,} bytes, the limit is {SIZE_TARGET:,}: nothing written")
    parity["html_sha256"] = hashlib.sha256(html.encode("utf-8")).hexdigest()
    with open(os.path.join(project_dir, "explorer.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    with open(os.path.join(project_dir, "explorer_parity.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(_finite(parity), f, indent=1, sort_keys=True)
        f.write("\n")
    return {"path": os.path.join(project_dir, "explorer.html"), "size_bytes": size, "size_target": SIZE_TARGET,
            "external_refs": refs, "parity": parity, "engine_sha256": engine_sha}


def main(argv):
    try:
        argv, _ = sd_paths.extract_flag(argv)
    except sd_paths.PathError as e:
        print(f"REFUSED: {e}")
        return 1
    if len(argv) != 2:
        print(__doc__)
        return 2
    project = sd_paths.resolve_project(argv[1])
    problem = sd_paths.project_problem(project, need_spec=False)      # a folder that fails the release gate keeps the gate's own message
    if problem:
        print(f"REFUSED: {problem}")
        return 1
    sd_paths.adopt_parent(project)
    try:
        rep = build(project)
    except (Refused, explorer_meta.MissingMetadata, explorer_config.ConfigError, export_js.Unsupported) as e:
        print(f"REFUSED: {e}")
        return 1
    p = rep["parity"]
    print(f"wrote {rep['path']} ({rep['size_bytes']:,} bytes; target < {SIZE_TARGET:,})")
    print(f"parity vs PySD: {p['n_runs']} runs ({p['n_random']} random), {p['n_series']} series; "
          f"max scale-relative A = {p['max_scale_rel']:.3e}, max pointwise B = {p['max_pointwise_rel']:.3e}; "
          f"headline metrics: {p['headline']['n_values']} values, max relative {p['headline']['max_rel']:.3e} "
          f"(tolerance {explorer_parity.TOL:g})")
    print("external references: none")
    return 0                                          # an over-size page is refused in build(), before anything is written


if __name__ == "__main__":
    sys.exit(main(sys.argv))
