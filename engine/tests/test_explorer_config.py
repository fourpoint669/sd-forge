"""engine/explorer_config.py: default page settings (no questions asked)."""
import os

import pytest

import explorer_config as ec
import explorer_meta as em
import export_js
import validate

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def defaults(project):
    d = os.path.join(ROOT, "projects", project)
    spec = validate.load_spec(os.path.join(d, "validation.toml"))
    ir = export_js.load_ir(spec["model"]["py_path"])
    kinds = {k: v["kind"] for k, v in em.build_metadata(spec, ir, d)["variables"].items()}
    import tomllib
    return spec, kinds, tomllib.loads(ec.default_config(spec, kinds))


@pytest.mark.parametrize("project", ["bass-b2b-adoption", "saas-churn-vs-winrate"])
def test_default_grid_covers_outcome_every_stock_and_every_flow(project):
    spec, kinds, cfg = defaults(project)
    charts = cfg["charts"]
    assert charts[0]["kind"] == "outcome"
    panels = sum(len(c["vars"]) for c in charts)
    assert panels >= 4
    shown = {v for c in charts for v in c["vars"]}
    assert {k for k, v in kinds.items() if v in ("stock", "flow")} <= shown
    for c in charts:
        assert len(set(c["vars"])) == len(c["vars"])


def test_bass_small_model_keeps_stock_and_flow_grids_open():
    _, _, cfg = defaults("bass-b2b-adoption")
    assert [c["id"] for c in cfg["charts"]][:3] == ["outcome", "stocks", "flows"]
    assert all(c.get("open", True) for c in cfg["charts"])


def test_saas_key_charts_open_rest_collapsed_by_sector():
    spec, kinds, cfg = defaults("saas-churn-vs-winrate")
    charts = cfg["charts"]
    assert charts[0]["id"] == "outcome" and charts[0]["vars"] == ["ARR"]
    key = charts[1]
    assert key["id"] == "key" and key.get("open", True) is True
    assert set(key["vars"]) == set(spec["model"]["key_outputs"]) - {"ARR"}
    rest = charts[2:]
    assert rest and all(c["open"] is False and c["id"].startswith("sector:") for c in rest)
    sectors = list(spec["sectors"])
    assert [c["title"] for c in rest] == [s for s in sectors if any(c["title"] == s for c in rest)]
    for c in rest:
        assert all(v in spec["sectors"][c["title"]] for v in c["vars"])


def test_saas_decision_metric_and_headline():
    spec, _, cfg = defaults("saas-churn-vs-winrate")
    assert cfg["decision"]["metric"] == "arr_m60"
    assert cfg["decision"]["headline"][0] == "arr_m60"
    assert len(cfg["decision"]["headline"]) == 4


def test_unknown_name_fails(tmp_path):
    spec, kinds, _ = defaults("bass-b2b-adoption")
    (tmp_path / "explorer.toml").write_text('[decision]\nmetric = "nope"\nheadline = ["nope"]\n[[charts]]\nid="x"\n'
                                            'kind="outcome"\ntitle="x"\nvars=["Customers"]\n')
    with pytest.raises(ec.ConfigError, match="nope"):
        ec.load_config(str(tmp_path), spec, kinds)
