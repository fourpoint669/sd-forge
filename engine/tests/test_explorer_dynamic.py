"""Structure tab live behaviour (M3b) in headless Chromium, checked against independent PySD recomputations.

Rules under test (stated once, recomputed here from PySD):
  changed node  max_t |current(t) - baseline(t)| > 1e-6 x max(max_t |current|, max_t |baseline|)
  pooling       for each capacity-capped drain (stock S, time constant T, capacity C):
                demand = S / T, ratio = demand / C; binding(t) = ratio >= bind;
                build_up(t) = t >= window and (S(t) - S(t - window)) / max(|S(t - window)|, 1e-12) >= build;
                flagged = binding and build_up; binding_only = binding and not build_up (capacity binding, the stock
                not yet building up: shown as its own warning, never as all clear)
"""
import json
import os
import shutil
import subprocess

import numpy as np
import pytest

import _browser

import build_explorer as be
import explorer_parity as ep
import validate

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "js", "structure_dynamic.js")
PROJECTS = ["bass-b2b-adoption", "saas-churn-vs-winrate"]


@pytest.fixture(scope="module", params=PROJECTS)
def dyn(request, tmp_path_factory):
    node = _browser.node_with_playwright(request)
    project = request.param
    d = tmp_path_factory.mktemp("dyn") / project
    shutil.copytree(os.path.join(ROOT, "projects", project), d,
                    ignore=shutil.ignore_patterns("explorer.html", "explorer_parity.json"))
    be.build(str(d))
    spec = validate.load_spec(str(d / "validation.toml"))
    sets = [s for s in ep.lever_settings(spec, n_random=5, seed=7) if s[0] == "base" or s[0].startswith("random")]
    sf = d / "settings.json"
    sf.write_text(json.dumps({"pooling_settings": sets}))
    shots = os.environ.get("SD_EXPLORER_SHOTS")
    if shots:
        shots = os.path.join(shots, project)
        os.makedirs(shots, exist_ok=True)
    p = subprocess.run([node, SCRIPT, str(d / "explorer.html"), str(sf)] + ([shots] if shots else []),
                       capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stderr[-3000:]
    out = json.loads(p.stdout)
    html = open(d / "explorer.html", encoding="utf-8").read()
    out["_data"] = json.loads(be.extract_script(html, "sd-data"))
    out["_spec"], out["_project"], out["_sets"] = spec, project, sets
    return out


def test_no_errors(dyn):
    assert dyn["console_errors"] == []


def test_pipe_width_is_proportional_to_the_live_flow(dyn):
    for snap in ("snap_default", "snap_30"):
        pipes = dyn[snap]["pipes"]
        assert pipes
        for p in pipes:
            assert p["rate"] == p["want"], p["name"]
            assert p["scale"] > 0
            assert abs((p["width"] - 2) / 14 - abs(p["rate"]) / p["scale"]) < 1e-9, p["name"]


def test_motion_speed_is_proportional_to_the_live_flow(dyn):
    moving = [p for p in dyn["snap_30"]["pipes"] if p["rate"] != 0]
    assert moving and all(p["anim"] != "none" for p in moving)
    k = [float(p["duration"]) * abs(p["rate"]) / p["scale"] for p in moving]
    assert max(k) - min(k) < 1e-6 * max(k)


def test_reduced_motion_shows_static_widths_and_numbers(dyn):
    s = dyn["snap_reduced"]
    assert s["reduced"]
    assert all(p["anim"] == "none" for p in s["pipes"])
    assert s["values"] == len(s["pipes"]) > 0


def test_tank_level_and_baseline_ghost(dyn):
    for t in dyn["snap_30"]["tanks"]:
        assert abs(t["level"] - t["want"]) < 1e-9 and abs(t["ghost"] - t["ghost_want"]) < 1e-9, t["name"]


def test_change_versus_baseline_colouring(dyn):
    def sign(c, b):
        if abs(c - b) <= 1e-6 * max(abs(c), abs(b), 1e-12):
            return "0"
        return "+" if c > b else "-"
    for t in dyn["snap_30"]["tanks"]:
        assert t["change"] == sign(t["cur"], t["base"]), t["name"]
    for p in dyn["snap_30"]["pipes"]:
        assert p["change"] == sign(p["rate"], p["base"]), p["name"]


def test_scrubber_and_chart_crosshair_are_linked(dyn):
    assert dyn["scrubber"]["min"] == "0"
    assert dyn["snap_30"]["i"] == 30 and dyn["label_30"] == dyn["_spec"]["model"]["time_unit"] + " " + format(dyn["snap_30"]["time"], "g")
    assert dyn["cross_after_scrub"] == dyn["charts"]
    assert dyn["scrub_after_chart"] == "12"


def test_play_and_pause(dyn):
    assert dyn["play_pressed"] == "true" and dyn["after_play"] > 0 and dyn["paused_stable"]


def test_flows_table_equals_the_run(dyn):
    assert len(dyn["flow_rows"]) == len(dyn["_data"]["structure"]["pipes"])
    assert dyn["flow_table_check"]


def test_delay_list_equals_the_audit_with_its_reference_curve(dyn):
    want = [(d["stock"], str(d["order"]), d["tau"]) for d in dyn["_data"]["structure"]["delays"]]
    assert [(d["stock"], d["order"], d["tau"]) for d in dyn["delays"]] == want and want
    dt = dyn["_spec"]["model"]["time_step"]
    for d in dyn["delays"]:
        assert d["curve"]
        assert f"ideal continuous-time reference; the model uses Euler with dt = {dt:g}" in d["text"]


def _pysd_runs(spec, params_list):
    return validate.run_batch(spec["model"]["py_path"], [{"params": p} for p in params_list])


def test_ripple_marks_exactly_the_nodes_pysd_says_changed(dyn):
    spec = dyn["_spec"]
    cur, base = _pysd_runs(spec, [dyn["ripple_params"], dyn["ripple_baseline"]])
    want = []
    for col in cur.columns:
        a, b = cur[col].to_numpy(float), base[col].to_numpy(float)
        scale = max(np.max(np.abs(a)), np.max(np.abs(b)))
        if scale > 0 and np.max(np.abs(a - b)) > 1e-6 * scale:
            want.append(col)
    assert dyn["changed_nodes"] == sorted(want) and want
    assert dyn["ripple_classes"] > 0 and dyn["ripple_delays"] > 1


def _pool_flags(df, base_df, cap, th):
    S = df[cap["stock_name"]].to_numpy(float)
    ratio = (S / df[cap["tau_name"]].to_numpy(float)) / df[cap["cap_name"]].to_numpy(float)
    t = np.asarray(df.index, float)
    w = int(round(th["window"] / (t[1] - t[0])))
    build = np.zeros(len(S), bool)
    for i in range(w, len(S)):
        build[i] = (S[i] - S[i - w]) / max(abs(S[i - w]), 1e-12) >= th["build"]
    bind = ratio >= th["bind"]
    return {"binding": bind.tolist(), "build_up": build.tolist(), "flagged": (bind & build).tolist(),
            "binding_only": (bind & ~build).tolist()}


def test_pooling_flags_equal_a_pysd_recomputation(dyn):
    caps = dyn["_data"]["structure"]["pooling"]["capped"]
    if not caps:
        pytest.skip("not applicable: this model has no capacity-capped flow (delay audit), so no pooling flag exists")
    spec, th = dyn["_spec"], dyn["pooling_defaults"]
    params = [p for _, p in dyn["_sets"]] + [dyn["ripple_baseline"]]
    runs = _pysd_runs(spec, params)
    base = runs[-1]
    assert len(dyn["pooling"]) == len(dyn["_sets"]) == 6
    any_flag = False
    for (label, _), df, page in zip(dyn["_sets"], runs, dyn["pooling"]):
        # one flag set per capacity-capped flow, each covering every saved time step: an empty or short report fails
        assert len(page["flags"]) == len(caps), (label, len(page["flags"]), len(caps))
        for cap, got in zip(caps, page["flags"]):
            for key in ("binding", "build_up", "flagged", "binding_only"):
                assert len(got[key]) == len(df.index) > 0, (label, key, len(got[key]), len(df.index))
            want = _pool_flags(df, base, cap, th)
            assert got["binding"] == want["binding"], label
            assert got["build_up"] == want["build_up"], label
            assert got["flagged"] == want["flagged"], label
            assert got["binding_only"] == want["binding_only"], label
            any_flag |= any(want["flagged"])
            any_watch = any(want["binding_only"])
    print(f"\npooling: {len(dyn['pooling'])} settings compared; some flag raised: {any_flag}")


def test_pooling_panel_shows_thresholds_and_rankings(dyn):
    panel = dyn["pool_panel"]
    for text in [panel["flag"], dyn["flag_after_threshold"]] + panel["shares"] + panel["levels"]:
        assert "e+" not in text and "e-" not in text, text   # a growth from zero is told as two levels, not a percentage
    ids = [i for i, _ in panel["thresholds"]]
    groups = dyn["_data"]["structure"]["pooling"]["groups"]
    assert len(panel["shares"]) == sum(len(g["stocks"]) for g in groups)
    assert len(panel["levels"]) == len([n for n in dyn["_data"]["structure"]["nodes"].values() if n["kind"] == "stock"])
    if dyn["_data"]["structure"]["pooling"]["capped"]:
        assert ids == ["th-bind", "th-build", "th-window"]
    else:
        assert "no capacity-capped flow" in panel["flag"]


def test_mobile(dyn):
    sw, cw = dyn["mobile_scroll"]
    assert sw <= cw


def test_binding_but_not_building_is_its_own_warning(dyn):
    if not dyn["_data"]["structure"]["pooling"]["capped"]:
        pytest.skip("not applicable: this model has no capacity-capped flow (delay audit), so no pooling state exists")
    w = dyn["watch_state"]
    assert w["found"], "no month with capacity binding and no build-up in the current run"
    assert w["cls"] == "pool-flag watch"
    assert w["text"].startswith("⚠ Capacity binding, not yet building up")
    assert "No pooling flag" not in w["text"] and "all clear" not in w["text"].lower()
    c = dyn["clear_state"]
    if c["found"]:
        assert c["text"].startswith("No binding capacity") and c["cls"] == "pool-flag"
