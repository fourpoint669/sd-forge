"""Parity gate: the JS engine reproduces PySD. Metric fixed at approval (never loosened to make a run pass):
per series S = max_t |py|; A = max_t |js - py| / S <= 1e-9 (an all-zero series must match exactly);
B = max |js - py| / |py| over points with |py| >= 1e-6 * S, <= 1e-9.
These tests FAIL (never skip) when PySD or node is missing."""
import math
import os

import numpy as np
import pytest

import explorer_parity as ep
import export_js
import validate

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASS = os.path.join(ROOT, "projects", "bass-b2b-adoption")


def test_metric_constants_are_the_approved_ones():
    assert ep.TOL == 1e-9
    assert ep.POINTWISE_FLOOR == 1e-6


def test_metric_scale_relative():
    py = np.array([0.0, 10.0, 100.0])
    js = py + np.array([0.0, 0.0, 1e-8])
    m = ep.parity_metrics(py, js)
    assert m["scale"] == pytest.approx(1e-10)
    assert m["pointwise"] == pytest.approx(1e-10)


def test_metric_pointwise_ignores_points_below_floor():
    py = np.array([1e-9, 1000.0])          # 1e-9 < 1e-6 * 1000: excluded from B
    js = np.array([2e-9, 1000.0])
    m = ep.parity_metrics(py, js)
    assert m["pointwise"] == 0.0
    assert m["scale"] == pytest.approx(1e-12)


def test_metric_all_zero_series_must_match_exactly():
    assert ep.parity_metrics(np.zeros(3), np.zeros(3))["scale"] == 0.0
    assert ep.parity_metrics(np.zeros(3), np.array([0, 1e-300, 0]))["scale"] == math.inf


def test_metric_nonfinite_values_must_match_in_place():
    py = np.array([1.0, np.inf, np.nan])
    assert ep.parity_metrics(py, py.copy())["scale"] == 0.0
    assert ep.parity_metrics(py, np.array([1.0, np.inf, 1.0]))["scale"] == math.inf


def test_lever_settings_cover_base_random_corners_and_policies():
    spec = validate.load_spec(os.path.join(BASS, "validation.toml"))
    settings = ep.lever_settings(spec)
    labels = [s[0] for s in settings]
    assert labels[0] == "base"
    rnd = [p for lab, p in settings if lab.startswith("random")]
    assert len(rnd) >= 20
    for p in rnd:
        for k, v in spec["parameters"].items():
            assert v["low"] <= p[k] <= v["high"], k
    assert "corner low" in labels and "corner high" in labels and "domain low" in labels
    assert {f"policy: {pol['name']}" for pol in spec["policies"]} <= set(labels)
    assert ep.lever_settings(spec) == settings          # seeded, deterministic


def test_parity_bass_all_settings():
    spec = validate.load_spec(os.path.join(BASS, "validation.toml"))
    engine = export_js.emit_js(export_js.load_ir(spec["model"]["py_path"]))
    rep = ep.run_parity(spec, engine)
    print(f"\nbass parity: {rep['n_runs']} runs ({rep['n_random']} random), {rep['n_series']} series; "
          f"max scale-relative A = {rep['max_scale_rel']:.3e}, max pointwise B = {rep['max_pointwise_rel']:.3e}")
    assert rep["n_random"] >= 20
    assert rep["missing_columns"] == []
    assert rep["max_scale_rel"] <= ep.TOL
    assert rep["max_pointwise_rel"] <= ep.TOL
    assert rep["pass"] is True


def test_parity_detects_a_one_coefficient_change():
    spec = validate.load_spec(os.path.join(BASS, "validation.toml"))
    engine = export_js.emit_js(export_js.load_ir(spec["model"]["py_path"]))
    mutated = engine.replace("(1 - v_win_rate)", "(1.000001 - v_win_rate)")
    assert mutated != engine
    rep = ep.run_parity(spec, mutated, n_random=2)
    assert rep["pass"] is False
    assert rep["max_scale_rel"] > ep.TOL


def test_js_saas_reproduces_bass_regression_from_checks():
    """checks.py regression, in JS: SaaS with every new mechanism off equals Bass step for step (REG_TOL 1e-9)."""
    import json
    saas_dir = os.path.join(ROOT, "projects", "saas-churn-vs-winrate")
    chk = json.load(open(os.path.join(saas_dir, "checks_results.json")))["regression_vs_bass_b2b_adoption"]
    saas_spec = validate.load_spec(os.path.join(saas_dir, "validation.toml"))
    bass_spec = validate.load_spec(os.path.join(BASS, "validation.toml"))
    sp = {**validate.base_params(saas_spec), **chk["settings"], **chk["shared_params_from_example"]}
    opts = {"final_time": chk["months"], "saveper": chk["dt"]}
    s = ep.node_run(export_js.emit_js(export_js.load_ir(saas_spec["model"]["py_path"])), [{"params": sp, "opts": opts}])[0]
    b = ep.node_run(export_js.emit_js(export_js.load_ir(bass_spec["model"]["py_path"])),
                    [{"params": validate.base_params(bass_spec), "opts": opts}])[0]
    cs, cb = np.asarray(s["series"]["Customers"]), np.asarray(b["series"]["Customers"])
    assert len(cs) == len(cb) == chk["steps"]
    rel = float(np.max(np.abs(cs - cb)) / np.max(np.abs(cb)))
    print(f"\nJS regression SaaS vs Bass: {len(cs)} steps, max |diff| / max = {rel:.3e} (tolerance {chk['tolerance']})")
    assert rel <= chk["tolerance"]
