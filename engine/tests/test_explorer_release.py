"""Every shipped explorer page comes from a project that passed validation (the refusal gate), and still matches it.

engine/explorer_release.py: the build stamps the sha256 of every file the release rests on into the page and into
explorer_parity.json; shipped_errors() re-checks the gate and the stamp. check_repo.py runs the same check."""
import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

import explorer_release as er

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHIPPED = sorted(d for d in (os.path.join(ROOT, "projects", p) for p in os.listdir(os.path.join(ROOT, "projects")))
                 if os.path.exists(os.path.join(d, "explorer.html")))


def test_all_validated_projects_ship_a_page():
    assert [os.path.basename(d) for d in SHIPPED] == ["bass-b2b-adoption", "car-dealership-profit", "saas-churn-vs-winrate"]


@pytest.mark.parametrize("d", SHIPPED, ids=os.path.basename)
def test_every_shipped_page_comes_from_a_project_that_passed_validation(d):
    er.check_release(d)                         # the refusal gate passes on the project as it is now
    assert er.shipped_errors(d) == []           # and the page is the one built from exactly these files
    html = open(os.path.join(d, "explorer.html"), encoding="utf-8").read()
    stamp = er.page_data(html)["release"]
    assert stamp == json.load(open(os.path.join(d, "explorer_parity.json")))["release"]
    assert set(stamp["files"]) >= {"validation.toml", "validation_report.md", "validation_results.json"}
    assert any(k.endswith(".py") for k in stamp["files"]) and any(k.endswith(".mdl") for k in stamp["files"])
    if os.path.exists(os.path.join(d, "checks.py")):
        assert {"checks.py", "checks_results.json"} <= set(stamp["files"]) and "checks_results.json all_pass" in stamp["gate"]


@pytest.fixture
def shipped_copy(tmp_path):
    def make(name="saas-churn-vs-winrate"):
        dst = tmp_path / name
        shutil.copytree(os.path.join(ROOT, "projects", name), dst)
        assert er.shipped_errors(str(dst)) == []
        return str(dst)
    return make


def _edit_json(path, **kw):
    r = json.load(open(path))
    r.update(kw)
    json.dump(r, open(path, "w"))


def test_a_page_whose_project_no_longer_passes_is_flagged(shipped_copy):
    d = shipped_copy()
    _edit_json(os.path.join(d, "validation_results.json"), all_pass=False)
    errs = er.shipped_errors(d)
    assert any("not released" in e and "all_pass" in e for e in errs)
    assert any("validation_results.json changed" in e for e in errs)


def test_failed_project_checks_are_flagged(shipped_copy):
    d = shipped_copy()
    _edit_json(os.path.join(d, "checks_results.json"), all_pass=False)
    assert any("not released" in e and "checks_results.json" in e for e in er.shipped_errors(d))


def test_report_not_pass_is_flagged(shipped_copy):
    d = shipped_copy("bass-b2b-adoption")
    p = os.path.join(d, "validation_report.md")
    txt = open(p).read()     # read before opening for write (which truncates)
    assert "Overall: **PASS**" in txt
    open(p, "w").write(txt.replace("Overall: **PASS**", "Overall: **FAIL**"))
    assert any("not released" in e and "validation_report.md" in e for e in er.shipped_errors(d))


@pytest.mark.parametrize("rel", ["validation.toml", "model/*.py", "model/*.mdl"])
def test_changing_what_was_validated_after_the_build_is_flagged(shipped_copy, rel):
    import glob
    d = shipped_copy("bass-b2b-adoption")
    p = glob.glob(os.path.join(d, rel))[0]
    open(p, "a").write("\n")
    errs = er.shipped_errors(d)
    assert any("changed since the page was built" in e for e in errs), errs
    # a model or spec edit also fails the release gate: validation no longer covers it
    assert any("not released" in e and "changed after validation" in e for e in errs), errs


def test_a_page_not_built_by_the_build_is_flagged(shipped_copy):
    d = shipped_copy("bass-b2b-adoption")
    p = os.path.join(d, "explorer.html")
    open(p, "a").write("<!-- edited -->")
    assert any("not the page recorded" in e for e in er.shipped_errors(d))


def test_a_page_without_its_parity_record_is_flagged(shipped_copy):
    d = shipped_copy("bass-b2b-adoption")
    os.remove(os.path.join(d, "explorer_parity.json"))
    assert any("without a readable explorer_parity.json" in e for e in er.shipped_errors(d))


def test_a_failed_parity_record_is_flagged(shipped_copy):
    d = shipped_copy("bass-b2b-adoption")
    p = os.path.join(d, "explorer_parity.json")
    _edit_json(p, max_scale_rel=2e-9)
    assert any("parity gate not passed" in e for e in er.shipped_errors(d))


def test_page_stamp_must_equal_the_record(shipped_copy):
    d = shipped_copy("bass-b2b-adoption")
    p = os.path.join(d, "explorer_parity.json")
    r = json.load(open(p))
    r["release"]["gate"] = "something else"
    json.dump(r, open(p, "w"))
    assert any("release stamp differs" in e for e in er.shipped_errors(d))


def test_no_page_no_errors_but_orphan_record_is_flagged(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    assert er.shipped_errors(str(d)) == []
    (d / "explorer_parity.json").write_text("{}")
    assert er.shipped_errors(str(d)) == ["p: explorer_parity.json without explorer.html"]


def test_check_repo_runs_the_explorer_checks_and_can_require_pages():
    py = sys.executable
    for args in ([], ["--require-explorer"]):
        p = subprocess.run([py, "-I", os.path.join(ROOT, "engine", "check_repo.py")] + args, cwd=ROOT, capture_output=True, text=True)
        assert p.returncode == 0, p.stdout + p.stderr
        assert "explorers=3" in p.stdout


def test_a_project_without_its_delay_audit_is_refused_with_the_fix(shipped_copy):
    """The build used to die with a FileNotFoundError traceback when delay_audit.json was missing."""
    d = shipped_copy()
    os.remove(os.path.join(d, "delay_audit.json"))
    errs = er.shipped_errors(d)
    assert any("delay_audit.json is missing" in e and "delay_audit.py" in e for e in errs), errs
    with pytest.raises(er.Refused, match="delay_audit.json is missing"):
        er.check_release(d)
