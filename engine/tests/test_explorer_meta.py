"""engine/explorer_meta.py: provenance for every variable the explorer shows; missing metadata fails the build."""
import ast
import os

import pytest

import explorer_meta as em
import export_js
import validate

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASS = os.path.join(ROOT, "projects", "bass-b2b-adoption")
SAAS = os.path.join(ROOT, "projects", "saas-churn-vs-winrate")


def meta_for(project):
    spec = validate.load_spec(os.path.join(project, "validation.toml"))
    ir = export_js.load_ir(spec["model"]["py_path"])
    return em.build_metadata(spec, ir, project)


def test_register_row_with_parenthetical_suffix():
    rows = em.parse_register(open(os.path.join(SAAS, "assumptions_register.md")).read())
    r = rows["initial sales capacity"]
    assert r["unit"] == "Firm/Month" and r["confidence"] == "estimated"


def test_register_split_rows_with_shared_prefix_and_comma():
    rows = em.parse_register(open(os.path.join(SAAS, "assumptions_register.md")).read())
    assert rows["churn share phase 1"]["confidence"] == rows["churn share phase 2"]["confidence"] == "verified (definition)"
    assert rows["churn share phase 2"]["base"] == "0.5"
    assert "initial cooling off firms" in rows and "initial firms in evaluation" in rows


def test_register_table_with_id_column():
    rows = em.parse_register(open(os.path.join(SAAS, "assumptions_register.md")).read())
    assert rows["sales capacity growth rate"]["unit"] == "1/Year"


def test_model_limits_is_verbatim_section():
    text = open(os.path.join(SAAS, "summary.md")).read()
    lim = em.model_limits(text)
    assert lim.startswith("## Model limits")
    assert lim in text
    assert "**Sales capacity is illustrative.**" in lim
    assert lim.rstrip("\n") == lim.rstrip("\n").rstrip()  # no trailing heading of the next section
    assert "\n## " not in lim[3:]


def test_every_parameter_has_full_provenance_bass():
    meta = meta_for(BASS)
    spec = validate.load_spec(os.path.join(BASS, "validation.toml"))
    for name, v in spec["parameters"].items():
        m = meta["variables"][name]
        assert m["kind"] == "parameter"
        for key in ("unit", "definition", "source", "confidence"):
            assert m[key], (name, key)
        assert m["range"] == [v["low"], v["high"]]
        assert m["domain"] == v.get("domain")


def test_every_parameter_has_full_provenance_saas():
    meta = meta_for(SAAS)
    spec = validate.load_spec(os.path.join(SAAS, "validation.toml"))
    assert len(spec["parameters"]) == 28
    for name in spec["parameters"]:
        m = meta["variables"][name]
        for key in ("unit", "definition", "source", "confidence"):
            assert m[key], (name, key)


def test_illustrative_parameters_are_flagged():
    meta = meta_for(SAAS)
    assert meta["variables"]["total programme budget"]["illustrative"] is True     # register says so
    assert meta["variables"]["initial sales capacity"]["illustrative"] is True     # summary Model limits says so
    assert meta["variables"]["initial total market"]["illustrative"] is True
    assert meta["variables"]["win spend scale"]["illustrative"] is False
    assert meta_for(BASS)["variables"]["total market"]["illustrative"] is True


def test_variables_without_model_comment_take_the_glossary_definition():
    meta = meta_for(BASS)
    m = meta["variables"]["deals won"]
    assert m["kind"] in ("flow", "auxiliary")
    assert m["definition_source"] == "glossary"
    assert m["definition"] and m["definition"] != "Defined by its equation."
    assert m["equation"] == "deals won = deal closings × win rate"
    assert m["confidence"] == "computed"
    assert meta["variables"]["Customers"]["definition_source"] == "model"


@pytest.mark.parametrize("project,n", [(BASS, 6), (SAAS, 23)])
def test_glossary_covers_exactly_the_variables_without_a_model_comment(project, n):
    meta = meta_for(project)
    gl = [k for k, v in meta["variables"].items() if v["definition_source"] == "glossary"]
    assert len(gl) == n
    assert set(gl) == set(em.load_glossary(project))


def test_missing_glossary_entry_fails(tmp_path):
    import shutil
    proj = tmp_path / "p"
    shutil.copytree(BASS, proj)
    g = proj / "explorer_glossary.toml"
    g.write_text(g.read_text().replace('[variables."deals won"]', '[variables."unused placeholder"]'))
    with pytest.raises(em.MissingMetadata, match="deals won"):
        meta_for(str(proj))


def test_glossary_entry_for_a_variable_with_a_model_comment_fails(tmp_path):
    import shutil
    proj = tmp_path / "p"
    shutil.copytree(BASS, proj)
    with open(proj / "explorer_glossary.toml", "a") as f:
        f.write('\n[variables."Customers"]\ndefinition = "duplicate"\n')
    with pytest.raises(em.MissingMetadata, match="Customers"):
        meta_for(str(proj))


def test_glossary_file_declares_itself_explanatory():
    for project in (BASS, SAAS):
        text = open(os.path.join(project, "explorer_glossary.toml")).read()
        assert "not part of the validated model" in text.splitlines()[0]


def test_stock_equation_shows_integral_of_flows():
    m = meta_for(BASS)["variables"]["Customers"]
    assert m["kind"] == "stock"
    assert m["equation"] == "Customers = ∫ (deals won − churn) dt, initial value: initial customers"


def test_every_component_has_unit_and_definition():
    for project in (BASS, SAAS):
        meta = meta_for(project)
        for name, m in meta["variables"].items():
            assert m["unit"] and m["definition"] and m["source"] and m["confidence"], name


def test_missing_register_row_fails_naming_the_parameter(tmp_path):
    import shutil
    proj = tmp_path / "p"
    shutil.copytree(BASS, proj)
    reg = proj / "assumptions_register.md"
    reg.write_text("\n".join(l for l in reg.read_text().splitlines() if not l.startswith("| cool off time")))
    with pytest.raises(em.MissingMetadata, match="cool off time"):
        meta_for(str(proj))


def test_equation_text_operators():
    names = {"a": "alpha", "b": "beta"}
    node = ast.parse("float(np.maximum(0, a() - b())) / a() ** 2", mode="eval").body
    assert em.equation_text(node, names) == "max(0, alpha − beta) / alpha^2"


@pytest.mark.parametrize("src, want", [
    ("10568557.06", "10568557.06"),          # %g gave 1.05686e+07
    ("9511701.353", "9511701.353"),
    ("82.69692513", "82.69692513"),
    ("3000000.0", "3000000"),                # a whole number stays plain, as it was
    ("18", "18"),
    ("0.1", "0.1"),
])
def test_equation_text_keeps_the_number_the_model_holds(src, want):
    """For a constant this text is the only place the page shows the value, so rounding it is wrong."""
    assert em.equation_text(ast.parse(src, mode="eval").body, {}) == want


def test_no_shipped_equation_text_rounds_a_constant_away():
    for project in (BASS, SAAS):
        for name, m in meta_for(project)["variables"].items():
            eq = m.get("equation") or ""
            assert "e+0" not in eq and "e-0" not in eq, (project, name, eq)
