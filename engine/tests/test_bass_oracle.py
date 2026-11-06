"""Analytic oracle: PySD-simulated Bass diffusion vs the closed form
F(t) = (1 - exp(-(p+q)t)) / (1 + (q/p) exp(-(p+q)t)) and peak time t* = ln(q/p)/(p+q).

Choice of dt and tolerance (engine/tests docs in the hardening plan): the fixture integrates with
Euler, so the error in F is first order, |F_sim - F| ~ C (p+q) dt. A numpy replica of the fixture
measured C in [0.07, 0.44] over these pairs, and a peak offset <= 1.72 dt. Hence:
  dt   = largest power of two <= 0.01 / (p+q)   (~100 steps per diffusion time constant, exact grid)
  F    : max |Adopters/N - F| <= 0.6 (p+q) dt    (1.36x the worst measured constant)
  order: err(dt) / err(dt/2) in [1.8, 2.2]       (residual is discretisation error, not structure)
  peak : |t_peak - t*| <= 3 dt
The F and peak tests are characterization tests of the oracle (they pass on the existing engine);
test_oracle_rejects_wrong_model shows the tolerance discriminates.
"""
import math

import numpy as np
import pytest

import validate
from conftest import BASS, mdl_text

N = 1000.0
PAIRS = [(0.03, 0.38), (0.01, 0.5), (0.05, 0.2), (0.003, 0.4)]


@pytest.fixture(scope="module")
def bass_py(tmp_path_factory):
    d = tmp_path_factory.mktemp("oracle")
    p = d / "bass.mdl"
    p.write_text(mdl_text(BASS, final_time=30, time_step=0.0625))
    return validate.translate(str(p), str(d))


def _dt(p, q):
    return 2.0 ** math.floor(math.log2(0.01 / (p + q)))


def _horizon(p, q):
    return float(math.ceil(10 / (p + q)))


def _run(py, p, q, dt, q_model=None):
    run = {"params": {"p": p, "q": q if q_model is None else q_model, "total population": N},
           "time_step": dt, "final_time": _horizon(p, q), "saveper_dt": True}
    df = validate.run_batch(py, [run], workers=1)[0]
    assert df is not None, validate.run_batch.last_errors
    return df


def _f_error(df, p, q):
    f = validate.bass_cumulative(df.index, p, q, 1.0)
    return float(np.max(np.abs(np.asarray(df["Adopters"], float) / N - f)))


@pytest.mark.parametrize("p,q", PAIRS)
def test_bass_matches_closed_form(bass_py, p, q):
    dt = _dt(p, q)
    e1 = _f_error(_run(bass_py, p, q, dt), p, q)
    e2 = _f_error(_run(bass_py, p, q, dt / 2), p, q)
    assert e1 <= 0.6 * (p + q) * dt, (e1, 0.6 * (p + q) * dt)
    assert 1.8 <= e1 / e2 <= 2.2, e1 / e2


@pytest.mark.parametrize("p,q", PAIRS)
def test_bass_peak_time_matches_analytic(bass_py, p, q):
    dt = _dt(p, q)
    df = _run(bass_py, p, q, dt)
    t_peak = float(df.index[int(np.argmax(np.asarray(df["adoption"], float)))])
    assert abs(t_peak - validate.bass_peak_time(p, q)) <= 3 * dt, (t_peak, validate.bass_peak_time(p, q))


def test_bass_q_below_p_has_no_interior_peak(bass_py):
    p, q = 0.2, 0.1
    dt = _dt(p, q)
    df = _run(bass_py, p, q, dt)
    assert int(np.argmax(np.asarray(df["adoption"], float))) == 0
    assert _f_error(df, p, q) <= 0.6 * (p + q) * dt
    with pytest.raises(ValueError, match="q > p"):
        validate.bass_peak_time(p, q)


def test_oracle_rejects_wrong_model(bass_py):
    """A model whose imitation rate is 5% off must fall outside the oracle tolerance."""
    p, q = 0.03, 0.38
    dt = _dt(p, q)
    err = _f_error(_run(bass_py, p, q, dt, q_model=q * 1.05), p, q)
    assert err > 0.6 * (p + q) * dt, (err, 0.6 * (p + q) * dt)
