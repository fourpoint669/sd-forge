"""Mutation test for checks.py: the regression check must catch a term that should be neutral under the regression
settings but is not. Run: .venv/bin/python -I -m pytest projects/saas-churn-vs-winrate/test_checks.py -q"""
import importlib.util
import os
import shutil
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import validate  # noqa: E402

spec_ = importlib.util.spec_from_file_location("checks", os.path.join(HERE, "checks.py"))
checks = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(checks)

STOCK = "CS Capacity=\n\tINTEG (CS capacity change, 0)"


def _copy_project(tmp_path, mutate=None):
    """Copy validation.toml and the .mdl into tmp_path, optionally mutate the .mdl text, translate it there."""
    d = tmp_path / "proj"
    (d / "model").mkdir(parents=True)
    shutil.copy(os.path.join(HERE, "validation.toml"), d / "validation.toml")
    text = open(os.path.join(HERE, "model", "saas_churn_vs_winrate.mdl")).read()
    if mutate:
        assert text.count(mutate[0]) == 1
        text = text.replace(*mutate)
    (d / "model" / "saas_churn_vs_winrate.mdl").write_text(text)
    validate.translate(str(d / "model" / "saas_churn_vs_winrate.mdl"), str(d / "model"))
    return validate.load_spec(str(d / "validation.toml"))


def test_regression_passes_on_the_unmutated_model(tmp_path):
    r = checks.regression(_copy_project(tmp_path))
    assert r["pass"] is True and r["max_abs_diff"] == 0


@pytest.mark.parametrize("mutation", [
    # CS Capacity should start empty; starting at 50 firms gives a churn reduction even with zero budget
    (STOCK, "CS Capacity=\n\tINTEG (CS capacity change, minimum customer base * 50)"),
    # the negative word-of-mouth term should vanish when the multiplier is 0; a constant offset keeps it alive
    ("MAX(0, customer share - negative word of mouth multiplier * detractor share)",
     "MAX(0, customer share - (negative word of mouth multiplier + 0.5) * detractor share)"),
])
def test_regression_fails_when_a_neutral_term_is_nonzero(tmp_path, mutation):
    r = checks.regression(_copy_project(tmp_path, mutation))
    assert r["pass"] is False
    assert r["rel_diff"] > checks.REG_TOL
