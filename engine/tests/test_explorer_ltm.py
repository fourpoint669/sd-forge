"""Live link and loop strength (M3c): the page's JavaScript link and loop scores against engine/loop_detector.py.

Gate (fixed metric, as for the engine): per series S = max_t |py|; max_t |js - py| / S <= 1e-9 (all-zero series must
match exactly; non-finite values must match in place), for every link-score series and every loop's relative score,
on the base case and 5 seeded random lever settings. 'end to end' = JS engine run + JS scores vs PySD run +
loop_detector; 'implementation' = JS scores computed from the PySD run's own values (isolates the port)."""
import json
import os

import pytest

import explorer_ltm as el
import validate

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module", params=["bass-b2b-adoption", "saas-churn-vs-winrate"])
def gate(request):
    d = os.path.join(ROOT, "projects", request.param)
    spec = validate.load_spec(os.path.join(d, "validation.toml"))
    rep = el.run_ltm_gate(spec, d)
    print(f"\n{request.param}: {rep['n_runs']} runs, {rep['n_link_series']} link series, {rep['n_loop_series']} loop series; "
          f"end to end: links {rep['end_to_end']['max_link']:.3e}, loops {rep['end_to_end']['max_loop']:.3e}; "
          f"implementation: links {rep['implementation']['max_link']:.3e}, loops {rep['implementation']['max_loop']:.3e}; "
          f"pass {rep['pass']}")
    return request.param, d, spec, rep


def test_gate_covers_base_and_five_random_settings(gate):
    _, _, spec, rep = gate
    assert rep["labels"] == ["base"] + [f"random {i}" for i in range(1, 6)]
    assert rep["n_loop_series"] == rep["n_runs"] * len(spec["loops"])
    assert rep["n_link_series"] > 0


def test_port_matches_loop_detector_on_identical_values(gate):
    _, _, _, rep = gate
    assert rep["implementation"]["max_link"] <= 1e-9 and rep["implementation"]["max_loop"] <= 1e-9


def test_gate_decision_is_recorded_with_its_numbers(gate):
    _, _, _, rep = gate
    assert rep["pass"] == (rep["end_to_end"]["max_link"] <= 1e-9 and rep["end_to_end"]["max_loop"] <= 1e-9)
    assert rep["mode"] == ("live" if rep["pass"] else "precomputed")


def test_customer_restricted_dominance_matches_gate8_at_base():
    d = os.path.join(ROOT, "projects", "saas-churn-vs-winrate")
    spec = validate.load_spec(os.path.join(d, "validation.toml"))
    got = el.js_restricted_dominance(spec, d, "Customers")
    want = json.load(open(os.path.join(d, "gate8_results.json")))["dominance_customer_loops_base_run"]
    assert [(p["start"], p["end"], p["loop"]) for p in got] == [(p["start"], p["end"], p["loop"]) for p in want]


def test_gate_fails_on_a_wrong_port():
    d = os.path.join(ROOT, "projects", "bass-b2b-adoption")
    spec = validate.load_spec(os.path.join(d, "validation.toml"))
    good = open(el.LTM_JS, encoding="utf-8").read()
    bad = good.replace("Math.abs(dxz / dz[k4]) * Math.sign(dxz / dx)", "Math.abs(dxz / dz[k4])")   # drops the sign
    assert bad != good
    rep = el.run_ltm_gate(spec, d, ltm_text=bad)
    assert rep["pass"] is False and rep["mode"] == "precomputed"
