"""engine/contrast_check.py: WCAG AA contrast of the explorer's colour tokens, both themes."""
import contrast_check as cc


def test_ratio_known_values():
    assert round(cc.ratio("#000000", "#ffffff"), 2) == 21.0
    assert round(cc.ratio("#777777", "#ffffff"), 2) == 4.48


def test_both_themes_parsed_and_dark_blocks_identical():
    themes = cc.load_themes()
    assert set(themes) == {"light", "dark"}
    assert themes["light"]["--ink"] != themes["dark"]["--ink"]


def test_all_pairs_meet_aa(capsys):
    rows = cc.check()
    print("\n" + cc.report(rows))
    assert len(rows) >= 2 * 14
    failing = [r for r in rows if not r["pass"]]
    assert failing == []


def test_scenario_series_are_colorblind_separable():
    rows = cc.check_series()
    print("\n" + "\n".join(f"{r['theme']} {r['a']} vs {r['b']}: normal {r['normal']:.1f}, worst CVD {r['cvd']:.1f} ({r['cvd_type']})"
                            for r in rows))
    assert rows and all(r["normal"] >= cc.NORMAL_FLOOR and r["cvd"] >= cc.CVD_FLOOR for r in rows)
