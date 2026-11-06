"""engine/loop_detector.py: loop enumeration, polarity and LTM dominance against analytic results."""
import numpy as np

import loop_detector as ld
import validate
from conftest import BASS, EXPONENTIAL, LOGISTIC, NO_LOOP


def _analyze(build, name, eqs, **kw):
    py = build(name, eqs, **kw)
    df = validate.run_batch(py, [{"saveper_dt": True}])[0]
    m = ld.parse_model(py)
    return m, df, ld.analyze(m, ld.values_from_frame(m, df))


def test_exponential_single_reinforcing_loop(build):
    _, _, r = _analyze(build, "expo", EXPONENTIAL)
    assert len(r["loops"]) == 1
    assert r["loops"][0]["polarity"] == "R"
    assert set(r["loops"][0]["variables"]) == {"Stock", "growth"}
    # the only loop dominates the whole run with relative score +1
    assert all(p["loop"] == "L1" for p in r["dominance"])
    assert abs(r["dominance"][0]["mean_relative_score"] - 1) < 1e-9


def test_logistic_dominance_switches_at_half_capacity(build):
    """Analytic: |R|/|B| = (1 - S/K)/(S/K), so dominance passes from R to B at S = K/2."""
    m, df, r = _analyze(build, "logi", LOGISTIC, final_time=30, time_step=0.01)
    pol = {frozenset(d["variables"]): d["polarity"] for d in r["loops"]}
    assert pol == {frozenset({"Population", "net growth"}): "R",
                   frozenset({"Population", "net growth", "fractional growth"}): "B"}
    periods = [p for p in r["dominance"] if p["loop"]]
    first = periods[0]
    assert r["loops"][int(first["loop"][1:]) - 1]["polarity"] == "R"
    s_switch = float(np.interp(first["end"], df.index, df["Population"]))
    assert abs(s_switch - 500) / 1000 < 0.02, s_switch
    assert r["loops"][int(periods[1]["loop"][1:]) - 1]["polarity"] == "B"


def test_bass_three_classic_loops(build):
    _, _, r = _analyze(build, "bass", BASS, final_time=30, time_step=0.01)
    pol = sorted((d["polarity"], len(d["variables"])) for d in r["loops"])
    assert pol == [("B", 3), ("B", 3), ("R", 4)]
    # word of mouth (R) dominates early, saturation (B) late
    first, last = r["dominance"][0], r["dominance"][-1]
    by_id = {d["id"]: d for d in r["loops"]}
    assert by_id[first["loop"]]["polarity"] == "R"
    assert by_id[last["loop"]]["polarity"] == "B"


def test_model_without_feedback_has_no_loops(build):
    _, _, r = _analyze(build, "noloop", NO_LOOP)
    assert r["loops"] == [] and r["dominance"] == []


def test_relative_scores_bounded(build):
    _, _, r = _analyze(build, "bass2", BASS, final_time=30, time_step=0.05)
    for v in r["relative_scores"].values():
        a = np.array([x for x in v if x == x])
        assert np.all(np.abs(a) <= 1 + 1e-12)


def test_unsupported_expression_is_reported_not_guessed():
    import ast
    expr = ast.parse("some_lookup(x())", mode="eval").body
    try:
        ld.compile_expr(expr, {"x"})
    except ld.Unsupported:
        return
    raise AssertionError("expected Unsupported")


# ---------------------------------------------------------------- hand-derived loop structures
from conftest import BASS_SINGLE, CHAIN, RING3, SIR  # noqa: E402


def _cycle(*names):
    """Directed edges of the cycle names[0] -> names[1] -> ... -> names[0]."""
    return frozenset(zip(names, names[1:] + names[:1]))


def _loops(r):
    return {(_cycle(*d["variables"]), d["polarity"]) for d in r["loops"]}


def test_bass_single_flow_has_one_R_and_one_B(build):
    _, _, r = _analyze(build, "bass1", BASS_SINGLE, final_time=30, time_step=0.01)
    assert _loops(r) == {
        (_cycle("Potential Adopters", "adoption"), "B"),
        (_cycle("Adopters", "adopter fraction", "adoption"), "R"),
    }


def test_bass_split_flow_loops_hand_derived(build):
    _, _, r = _analyze(build, "bass3", BASS, final_time=30, time_step=0.01)
    assert _loops(r) == {
        (_cycle("Adopters", "adopter fraction", "adoption from word of mouth", "adoption"), "R"),
        (_cycle("Potential Adopters", "adoption from word of mouth", "adoption"), "B"),
        (_cycle("Potential Adopters", "adoption from advertising", "adoption"), "B"),
    }


def test_sir_loops_hand_derived(build):
    _, _, r = _analyze(build, "sir", SIR, final_time=60, time_step=0.01, time_unit="Day")
    assert _loops(r) == {
        (_cycle("Susceptible", "infection"), "B"),
        (_cycle("Infected", "infection"), "R"),
        (_cycle("Infected", "recovery"), "B"),
    }
    assert not any("Recovered" in d["variables"] for d in r["loops"])


def test_acyclic_models_have_no_loops(build):
    for name, eqs in (("noloop2", NO_LOOP), ("chain", CHAIN)):
        m, _, r = _analyze(build, name, eqs)
        assert ld.find_loops(m) == ([], False)
        assert r["loops"] == [] and r["dominance"] == []


def test_distinct_cycles_on_same_vertices(build):
    _, _, r = _analyze(build, "ring3", RING3, final_time=10, time_step=0.0625)
    fwd = _cycle("A", "flow B", "B", "flow C", "C", "flow A")
    rev = _cycle("A", "flow C", "C", "flow B", "B", "flow A")
    assert _loops(r) == {
        (_cycle("A", "flow B", "B", "flow A"), "R"), (_cycle("A", "flow C", "C", "flow A"), "R"),
        (_cycle("B", "flow C", "C", "flow B"), "R"), (fwd, "R"), (rev, "R"),
    }
    declared = [{"name": "forward", "polarity": "R", "variables": ["A", "flow B", "B", "flow C", "C", "flow A"]},
                {"name": "reverse", "polarity": "R", "variables": ["B", "flow A", "A", "flow C", "C", "flow B"]},
                {"name": "ab", "polarity": "R", "variables": ["A", "flow B", "B", "flow A"]},
                {"name": "ac", "polarity": "R", "variables": ["A", "flow C", "C", "flow A"]},
                {"name": "bc", "polarity": "R", "variables": ["B", "flow C", "C", "flow B"]}]
    probs, names = validate.match_loops(r["loops"], declared)
    assert probs == []
    by_edges = {_cycle(*d["variables"]): names[d["id"]] for d in r["loops"]}
    assert by_edges[fwd] == "forward" and by_edges[rev] == "reverse"


def test_match_loops_direction_and_duplicates():
    found = [{"id": "L1", "polarity": "R", "variables": ["A", "flow B", "B", "flow C", "C", "flow A"]}]
    ok = [{"name": "fwd", "polarity": "R", "variables": ["C", "flow A", "A", "flow B", "B", "flow C"]}]   # rotation
    assert validate.match_loops(found, ok) == ([], {"L1": "fwd"})
    backwards = [{"name": "fwd", "polarity": "R", "variables": ["flow A", "C", "flow C", "B", "flow B", "A"]}]
    probs, names = validate.match_loops(found, backwards)
    assert "declared loop 'fwd' lists its variables against the model's causal direction" in probs
    assert names == {"L1": None}
    dup = ok + [{"name": "again", "polarity": "R", "variables": ["A", "flow B", "B", "flow C", "C", "flow A"]}]
    probs, _ = validate.match_loops(found, dup)
    assert "declared loops 'fwd' and 'again' are the same cycle" in probs
    wrong = [dict(ok[0], polarity="B")]
    assert "'fwd' declared B, detected R" in validate.match_loops(found, wrong)[0]
