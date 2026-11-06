"""/sd-explorer intake (engine/explorer_intake.py): one round of up to 4 skippable multiple-choice questions; skipping
all still builds a valid page; every setting, assumed or chosen, is listed in the page's Model limits dialog; the
refusal gates are untouched."""
import json
import re
import os
import shutil
import subprocess
import sys
import tomllib

import pytest

import _browser

import build_explorer as be
import explorer_intake as ei
import explorer_release as er

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASS = os.path.join(ROOT, "projects", "bass-b2b-adoption")
SAAS = os.path.join(ROOT, "projects", "saas-churn-vs-winrate")
SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "js", "intake.js")


def _check_questions(qs):
    assert 1 <= len(qs) <= 4
    assert [q["id"] for q in qs] == ["projects", "decision", "levers", "audience"]
    for q in qs:
        keys = [o["key"] for o in q["options"]]
        assert 2 <= len(keys) <= 4 and len(set(keys)) == len(keys), q["id"]
        assert q["default"] in keys and "(default)" in q["options"][keys.index(q["default"])]["label"], q["id"]
        assert len(q["header"]) <= 12 and all(o["description"] for o in q["options"])


@pytest.mark.parametrize("dirs", [[BASS], [SAAS], [], [BASS, SAAS]], ids=["bass", "saas", "none", "both"])
def test_one_round_of_at_most_four_multiple_choice_questions_with_defaults(dirs):
    _check_questions(ei.questions(dirs))


def test_questions_cli_prints_json():
    p = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "engine", "explorer_intake.py"), "questions", SAAS],
                       capture_output=True, text=True, check=True)
    _check_questions(json.loads(p.stdout))


def test_every_question_skipped_means_every_setting_assumed():
    s = ei.resolve(SAAS, {})
    assert all(s[k]["source"] == ei.ASSUMED for k in ("projects", "decision", "levers", "audience"))
    assert s["decision"]["metric"] == "arr_m60" and s["decision"]["baseline"] == "no programme"
    assert s["levers"]["value"] == "all" and s["audience"]["value"] == "decision-makers"


def test_answers_are_checked_against_the_options():
    with pytest.raises(ei.IntakeError):
        ei.resolve(SAAS, {"decision": "metric:no_such_metric"})
    with pytest.raises(ei.IntakeError):
        ei.resolve(SAAS, {"audience": "everyone"})
    with pytest.raises(ei.IntakeError):
        ei.resolve(SAAS, {"colour": "blue"})


def test_unattended_records_defaults_whatever_was_passed(tmp_path):
    d = tmp_path / "saas"
    shutil.copytree(SAAS, d)
    ei.record(str(d), {"audience": "workshop"}, mode="unattended")
    t = tomllib.load(open(d / "explorer_intake.toml", "rb"))
    assert t["mode"] == "unattended" and t["audience"] == {"value": "decision-makers", "source": ei.ASSUMED}


def test_refusal_gates_unchanged_by_intake(tmp_path):
    d = tmp_path / "bass"
    shutil.copytree(BASS, d, ignore=shutil.ignore_patterns("explorer.html", "explorer_parity.json"))
    ei.record(str(d), {"levers": "policy"})
    r = json.load(open(d / "validation_results.json"))
    r["all_pass"] = False
    json.dump(r, open(d / "validation_results.json", "w"))
    with pytest.raises(be.Refused):
        be.build(str(d))


VARIANTS = {"no-intake-file": None, "all-skipped": {},
            "chosen": {"decision": "metric:share_m60", "levers": "policy", "audience": "workshop"},
            "baseline-chosen": {"decision": "baseline:marketing reach +20%"}}


@pytest.fixture(scope="module", params=list(VARIANTS), ids=list(VARIANTS))
def built(request, tmp_path_factory):
    node = _browser.node_with_playwright(request)
    d = tmp_path_factory.mktemp("intake") / "bass-b2b-adoption"
    shutil.copytree(BASS, d, ignore=shutil.ignore_patterns("explorer.html", "explorer_parity.json", "explorer_intake.toml"))
    answers = VARIANTS[request.param]
    if answers is not None:
        ei.record(str(d), answers)
    be.build(str(d))
    html = open(d / "explorer.html", encoding="utf-8").read()
    p = subprocess.run([node, SCRIPT, str(d / "explorer.html")], capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stderr[-2000:]
    return {"variant": request.param, "dir": str(d), "data": er.page_data(html), "ui": json.loads(p.stdout)}


def test_page_is_valid_and_shipped_cleanly(built):
    assert er.shipped_errors(built["dir"]) == []
    assert built["ui"]["console_errors"] == []


def test_every_setting_appears_in_model_limits(built):
    lim = built["ui"]["limits"]
    assert lim["verbatim_first"] and "assumed or chosen" in lim["heading"]
    items = lim["items"]
    assert [i["text"].split(":")[0] for i in items] == ["Projects built", "Decision metric and baseline", "Levers that move", "Audience"]
    want = {"no-intake-file": [ei.ASSUMED] * 4, "all-skipped": [ei.ASSUMED] * 4,
            "chosen": [ei.ASSUMED, ei.CHOSEN, ei.CHOSEN, ei.CHOSEN],
            "baseline-chosen": [ei.ASSUMED, ei.CHOSEN, ei.ASSUMED, ei.ASSUMED]}[built["variant"]]
    assert [i["source"] for i in items] == want
    assert all(f"({s})" in i["text"] for i, s in zip(items, want))
    mode = {"no-intake-file": "No intake was recorded", "all-skipped": "skipped question took its default", "chosen": "skipped question",
            "baseline-chosen": "skipped question"}
    assert mode[built["variant"]] in lim["note"]


def test_skipping_everything_gives_the_default_page(built):
    if built["variant"] not in ("no-intake-file", "all-skipped"):
        return
    ui, D = built["ui"]["first"], built["data"]
    assert ui["results_hidden"] is False and ui["structure_hidden"] is True
    assert ui["held"] == 0 and ui["sliders"] == len([l for l in D["levers"] if not l["fixed"]])
    assert D["decision"]["metric"] == "customers_m60" and D["baseline_default"] == "base"


def test_chosen_answers_shape_the_page(built):
    if built["variant"] != "chosen":
        return
    ui, D = built["ui"]["first"], built["data"]
    assert D["decision"]["metric"] == "share_m60" and D["decision"]["headline"][0] == "share_m60"
    assert ui["structure_hidden"] is False and ui["results_hidden"] is True      # workshop opens on Structure
    policy = {"marketing reach rate", "word of mouth rate", "annual logo churn rate", "sales cycle time", "win rate"}
    exposed = {l["name"] for l in D["levers"] if l["exposed"]}
    assert exposed <= policy | {l["name"] for l in D["levers"] if l["fixed"]} and exposed
    assert ui["held"] == len([l for l in D["levers"] if not l["exposed"] and not l["fixed"]]) > 0


def _page_labels(unit, metrics):
    """Run the page's own label code (app.js sentenceCase + metricLabelRaw) under node."""
    app = open(os.path.join(ROOT, "engine", "explorer_template", "app.js"), encoding="utf-8").read()
    fns = []
    for name in ("sentenceCase", "metricLabel", "metricLabelRaw"):
        i = app.index("  function " + name + "(")
        j = app.index("\n  }\n", i) + 4 if name != "metricLabel" else app.index("\n", i) + 1
        fns.append(app[i:j])
    js = "var TU = %s;\n%s\nprocess.stdout.write(JSON.stringify(%s.map(metricLabel)));" % (
        json.dumps(unit), "".join(fns), json.dumps(metrics))
    p = subprocess.run([shutil.which("node"), "-e", js], capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


@pytest.mark.parametrize("project", [BASS, SAAS], ids=["bass", "saas"])
def test_metric_labels_equal_the_page(project):
    if not shutil.which("node"):
        pytest.fail("node is required to read the page's label code")
    spec = tomllib.load(open(os.path.join(project, "validation.toml"), "rb"))
    unit, metrics = spec["model"]["time_unit"], spec["montecarlo"]["metrics"]
    assert [ei.metric_label(m, unit) for m in metrics] == _page_labels(unit, metrics)


@pytest.mark.parametrize("dirs", [[BASS], [SAAS], []], ids=["bass", "saas", "none"])
def test_intake_shows_display_text_not_internal_names(dirs):
    names = set()
    for d in (dirs or [BASS, SAAS]):
        names |= {m["name"] for m in tomllib.load(open(os.path.join(d, "validation.toml"), "rb"))["montecarlo"]["metrics"]}
    for q in ei.questions(dirs):
        for o in q["options"]:
            text = o["label"] + " " + o["description"]
            assert not any(re.search(r"\b" + re.escape(n) + r"\b", text) for n in names), text
            assert o["label"][:1].isupper(), o["label"]          # every option starts with a capital


def test_chosen_baseline_is_the_one_selected_in_the_dropdown(built):
    """Review finding 5: the Compare-against dropdown must show the baseline every number on the page is measured against."""
    if built["variant"] != "baseline-chosen":
        return
    ui, D = built["ui"]["first"], built["data"]
    assert D["baseline_default"] == "marketing reach +20%"
    assert ui["baseline"] == "marketing reach +20%"
    assert "Baseline: marketing reach +20%" in ui["compare_header"]


@pytest.fixture(scope="module")
def saas_base_values(tmp_path_factory):
    """Review round 2, finding 4: a SaaS page whose intake chose "base values" (a preset equals the base there)."""
    d = tmp_path_factory.mktemp("bv") / "saas-churn-vs-winrate"
    shutil.copytree(SAAS, d, ignore=shutil.ignore_patterns("explorer.html", "explorer_parity.json", "explorer_intake.toml"))
    ei.record(str(d), {"decision": "baseline:base values"})
    be.build(str(d))
    return str(d)


def test_base_values_baseline_selects_the_base_parameters(saas_base_values, request):
    node = _browser.node_with_playwright(request)
    js = r"""
const { chromium } = require("playwright");
(async () => { const b = await chromium.launch(); const p = await b.newPage();
  p.on("pageerror", (e) => console.log("PAGEERROR " + e));
  await p.goto("file://" + process.argv[1]); await p.waitForSelector(".tile");
  console.log(JSON.stringify(await p.evaluate(() => { const D = JSON.parse(document.getElementById("sd-data").textContent);
    const o = document.getElementById("baseline-select").selectedOptions[0], par = JSON.parse(o.getAttribute("data-params"));
    return { selected: o.textContent, equals_base: Object.keys(D.base).every((k) => par[k] === D.base[k]),
      header: [...document.querySelectorAll("#compare th")].map((t) => t.textContent).join(" | ") }; })));
  await b.close(); })();"""
    p = subprocess.run([node, "-e", js, os.path.join(saas_base_values, "explorer.html")], capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stderr[-1500:]
    out = json.loads(p.stdout.strip().splitlines()[-1])
    assert out["equals_base"] is True, out
    assert out["selected"] == "50/50 split (= base values)" and "Baseline: 50/50 split (= base values)" in out["header"], out
