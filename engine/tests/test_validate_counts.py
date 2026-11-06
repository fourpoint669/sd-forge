"""engine/validate.py count checks (approved after the fail-open audit). Fail-closed only: a healthy run is unchanged.
1. run_batch keeps one entry per requested run: a worker that returns fewer frames than its chunk leaves None for each
   missing run (a failed run), never a shorter list.
2. T3 fails when it has fewer results than extreme cases, instead of checking only the cases that came back."""
import os

import validate

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASS = os.path.join(ROOT, "projects", "bass-b2b-adoption")


def test_run_batch_keeps_one_entry_per_run_when_a_worker_returns_too_few(monkeypatch):
    spec = validate.load_spec(os.path.join(BASS, "validation.toml"))
    runs = [{"params": validate.base_params(spec), "final_time": 2, "time_step": 0.25, "saveper": 1} for _ in range(4)]
    real = validate._spawn

    def short_worker(job, timeout):
        res, data = real(job, timeout)
        if data is not None and len(job["runs"]) > 1:      # the worker loses its last run's frame
            last = len(job["runs"]) - 1
            data = {k: v for k, v in data.items() if k not in (f"run{last}", f"idx{last}")}
        return res, data
    monkeypatch.setattr(validate, "_spawn", short_worker)
    out = validate.run_batch(spec["model"]["py_path"], runs, workers=1)
    assert len(out) == len(runs)
    assert out[-1] is None and all(df is not None for df in out[:-1])


def test_run_batch_pads_a_short_chunk_with_failed_runs():
    out = [None] * 5
    errs = []
    validate._place_chunk(out, 1, 3, ["a", "b"], errs)        # a chunk of 3 runs came back with 2 frames
    assert out == [None, None, None, None, None] and len(out) == 5 and errs


def test_t3_fails_when_extreme_results_are_missing(monkeypatch):
    real = validate.run_batch
    calls = {"n": 0}

    def drop_last_extreme(py, runs, *a, **k):
        calls["n"] += 1
        out = real(py, runs, *a, **k)
        return out[:-1] if calls["n"] == 1 else out          # the first batch holds the deterministic and extreme runs
    monkeypatch.setattr(validate, "run_batch", drop_last_extreme)
    spec, R, _ = validate.run_all(os.path.join(BASS, "validation.toml"))
    t3 = R["tests"]["T3_extremes"]
    assert t3["pass"] is False and any("results for" in f for f in t3["failures"]), t3["failures"][:3]
    assert R["all_pass"] is False


# ---- validation_results.json is written on every exit path of validate.main
import json
import shutil

import pytest


def _copy(tmp_path):
    d = tmp_path / "bass-b2b-adoption"
    shutil.copytree(BASS, d, ignore=shutil.ignore_patterns("explorer*", "validation_results.json"))
    return d


def _results(d):
    return json.load(open(d / "validation_results.json"))


def test_json_written_on_early_stop(tmp_path):
    """T1c problem: run_all stops before any model run."""
    d = _copy(tmp_path)
    t = (d / "validation.toml").read_text().replace('[parameters."win rate"]\nbase = 0.21', '[parameters."win rate"]\nbase = 5', 1)
    assert "base = 5" in t
    (d / "validation.toml").write_text(t)
    assert validate.main([str(d / "validation.toml")]) == 1
    r = _results(d)
    assert r["all_pass"] is False and "fatal" in r and r["output_files"] == {}


def test_json_written_when_the_spec_is_unreadable(tmp_path):
    d = _copy(tmp_path)
    (d / "validation.toml").write_text("this is [not toml")
    assert validate.main([str(d / "validation.toml")]) == 1
    r = _results(d)
    assert r["all_pass"] is False and "fatal" in r


def test_json_written_when_writing_the_report_crashes(tmp_path):
    """A crash inside write_outputs (here: validation_report.md cannot be written) still replaces an earlier run's
    passing validation_results.json with a failed one."""
    d = _copy(tmp_path)
    t = (d / "validation.toml").read_text().replace('[parameters."win rate"]\nbase = 0.21', '[parameters."win rate"]\nbase = 5', 1)
    (d / "validation.toml").write_text(t)
    (d / "validation_results.json").write_text(json.dumps({"all_pass": True, "stale": "from an earlier run"}))
    (d / "validation_report.md").unlink()
    (d / "validation_report.md").mkdir()           # opening it for writing raises inside write_outputs
    with pytest.raises((IsADirectoryError, PermissionError)):      # Windows raises PermissionError for a directory
        validate.main([str(d / "validation.toml")])
    r = _results(d)
    assert r["all_pass"] is False and "stale" not in r and "write_outputs failed" in r["fatal"]
