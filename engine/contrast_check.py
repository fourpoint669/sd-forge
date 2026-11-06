"""WCAG 2.x contrast report for the sd-explorer colour tokens (engine/explorer_template/style.css), both themes.

Usage:  python -I engine/contrast_check.py      (prints every pair and its ratio; exit 1 if any pair fails AA)

Text pairs need 4.5:1 (AA, normal text); graphical objects and UI component boundaries need 3:1 (WCAG 1.4.11).
The dark theme is defined twice (prefers-color-scheme media block and [data-theme="dark"]); both must be identical.
"""
import os
import re
import sys

CSS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "explorer_template", "style.css")
TEXT = [("--ink", s) for s in ("--surface", "--surface-2", "--page")] + \
       [("--ink-2", s) for s in ("--surface", "--surface-2", "--page")] + \
       [("--muted", s) for s in ("--surface", "--surface-2", "--page")] + \
       [("--accent-ink", s) for s in ("--surface", "--surface-2", "--page")] + \
       [("--warn-ink", "--warn-bg"), ("--on-accent", "--accent")]
# Opaque endpoint of the bounded glass backdrop; the other endpoint is --surface.
TEXT += [(t, "--chrome-bound") for t in ("--ink", "--ink-2", "--muted", "--accent-ink")]
SERIES = ["--series-current", "--series-a", "--series-b", "--series-c", "--series-d"]
GRAPHIC = [("--control-border", "--surface"), ("--control-border", "--surface-2"), ("--accent", "--surface"),
           ("--series-baseline", "--surface"), ("--warn-border", "--warn-bg")] + [(s, "--surface") for s in SERIES] + \
          [("--diagram-ink", "--page"), ("--diagram-ink", "--surface"), ("--pipe", "--page"), ("--loop-r", "--surface"),
           ("--loop-b", "--surface"), ("--accent", "--page"), ("--chg-up", "--page"), ("--chg-down", "--page")]
GRAPHIC += [("--control-border", "--chrome-bound"), ("--accent", "--chrome-bound")]
# Colour-vision separation of the scenario lines (current run and saved scenarios A-D), all pairs: OKLab distance x 100
# with full-severity Machado (2009) simulation. Floors as in the dataviz method: 15 for normal vision (hard floor);
# CVD 8 is the target and 6-8 is acceptable only with secondary encoding (the page gives every saved scenario its
# own dash pattern and an end-of-line letter, and the legend names each line). Gated on protan and deutan (the common
# forms); tritan distance is reported, not gated, as the dataviz palette validator does.
NORMAL_FLOOR = 15.0
CVD_FLOOR = 6.0
CVD_TARGET = 8.0
MACHADO = {
    "protan": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
    "deutan": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
    "tritan": [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]],
}


def _lin(c):
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hexcol):
    h = hexcol.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _rgb_lin(hexcol):
    h = hexcol.lstrip("#")
    return [_lin(int(h[i:i + 2], 16)) for i in (0, 2, 4)]


def oklab(lin):
    r, g, b = (min(1.0, max(0.0, c)) for c in lin)
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)


def delta_e(a_lin, b_lin):
    return 100 * sum((x - y) ** 2 for x, y in zip(oklab(a_lin), oklab(b_lin))) ** 0.5


def simulate(lin, kind):
    m = MACHADO[kind]
    return [sum(m[i][j] * lin[j] for j in range(3)) for i in range(3)]


def check_series(path=CSS):
    """All pairs of scenario line colours, per theme: normal-vision and worst simulated-CVD distance."""
    rows = []
    for theme, tok in load_themes(path).items():
        for i, a in enumerate(SERIES):
            for b in SERIES[i + 1:]:
                la, lb = _rgb_lin(tok[a]), _rgb_lin(tok[b])
                cvd = min((delta_e(simulate(la, k), simulate(lb, k)), k) for k in ("protan", "deutan"))
                rows.append({"theme": theme, "a": a, "b": b, "normal": delta_e(la, lb), "cvd": cvd[0], "cvd_type": cvd[1],
                             "tritan": delta_e(simulate(la, "tritan"), simulate(lb, "tritan"))})
    return rows


def ratio(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _tokens(block):
    return dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})\s*;", block))


def load_themes(path=CSS):
    css = open(path, encoding="utf-8").read()
    light = re.search(r"^:root \{(.*?)^\}", css, re.S | re.M).group(1)
    media = re.search(r":root:where\(:not\(\[data-theme=\"light\"\]\)\) \{(.*?)\n  \}", css, re.S).group(1)
    dark = re.search(r"^:root\[data-theme=\"dark\"\] \{(.*?)^\}", css, re.S | re.M).group(1)
    if not _tokens(dark):
        raise ValueError("dark theme defines no colour tokens (a dark theme cannot silently reuse the light colours)")
    if _tokens(media) != _tokens(dark):
        raise ValueError("dark theme differs between the media query and [data-theme=dark]")
    lt = _tokens(light)
    return {"light": lt, "dark": {**lt, **_tokens(dark)}}


def check(path=CSS):
    rows = []
    for theme, tok in load_themes(path).items():
        for kind, pairs, need in (("text", TEXT, 4.5), ("graphic", GRAPHIC, 3.0)):
            for fg, bg in pairs:
                r = ratio(tok[fg], tok[bg])
                rows.append({"theme": theme, "kind": kind, "fg": fg, "bg": bg, "fg_hex": tok[fg], "bg_hex": tok[bg],
                             "ratio": r, "need": need, "pass": r >= need})
    return rows


def report(rows):
    out = [f"{'theme':6} {'kind':8} {'foreground':18} {'background':12} {'ratio':>6}  need  result"]
    for r in rows:
        out.append(f"{r['theme']:6} {r['kind']:8} {r['fg']:18} {r['bg']:12} {r['ratio']:6.2f}  {r['need']:.1f}  "
                   f"{'PASS' if r['pass'] else 'FAIL'}")
    return "\n".join(out)


def main():
    rows = check()
    print(report(rows))
    bad = [r for r in rows if not r["pass"]]
    print(f"{len(rows) - len(bad)}/{len(rows)} pairs meet WCAG AA")
    series = check_series()
    sbad = [r for r in series if r["normal"] < NORMAL_FLOOR or r["cvd"] < CVD_FLOOR]
    worst = min(series, key=lambda r: r["cvd"])
    print(f"scenario lines: {len(series)} pairs; worst CVD distance {worst['cvd']:.1f} ({worst['theme']}, {worst['a']} vs "
          f"{worst['b']}, {worst['cvd_type']}); worst normal-vision {min(r['normal'] for r in series):.1f}; floors: "
          f"normal {NORMAL_FLOOR:g}, CVD {CVD_FLOOR:g} with secondary encoding (target {CVD_TARGET:g}); "
          f"worst tritan (reported, not gated) {min(r['tritan'] for r in series):.1f}")
    return 1 if bad or sbad else 0


if __name__ == "__main__":
    sys.exit(main())
