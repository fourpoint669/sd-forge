"""Fan chart (Monte Carlo percentile bands) from a validated project's mc_bands.csv.

Usage:  python -I engine/fan_chart.py projects/<model>/mc_bands.csv <out.png> "<var>[:<title>[:<scale>]]" [...]
One small-multiple panel per variable (never a dual axis). Bands: P5-P95 (light), P25-P75 (mid),
median line. mc_bands.csv exists only when engine/validate.py passed every gating test; this script also
refuses to draw unless validation_results.json next to the CSV says all_pass.
Colors: one sequential hue (blue ramp of the dataviz reference palette).
"""
import csv
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
OUTER, INNER, MEDIAN = "#b7d3f6", "#6da7ec", "#1c5cab"   # blue steps 150 / 300 / 550


def validated(src):
    """True only if validation_results.json next to the bands says every gating test passed."""
    import json
    import os
    try:
        return json.load(open(os.path.join(os.path.dirname(os.path.abspath(src)), "validation_results.json"))).get("all_pass") is True
    except (OSError, ValueError):
        return False


def time_label(src):
    """x-axis label from time_unit in the validation.toml next to the bands ('Time (Day)'); 'Time' if there is none."""
    import os
    import tomllib
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(src)), "validation.toml"), "rb") as f:
            unit = tomllib.load(f)["model"]["time_unit"]
        return f"Time ({unit})"
    except (OSError, KeyError, ValueError):
        return "Time"


def number(v):
    """Thousands separators from 100 up; three significant digits below (0.73 must not print as 1)."""
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:.3g}"


def main(argv):
    src, out, specs = argv[0], argv[1], argv[2:]
    if not validated(src):
        sys.exit(f"refusing to draw {src}: validation has not passed (validation_results.json missing or not all_pass)")
    rows = list(csv.DictReader(open(src)))
    t = [float(r["time"]) for r in rows]
    fig, axes = plt.subplots(1, len(specs), figsize=(5.2 * len(specs), 3.6), dpi=150, facecolor=SURFACE)
    axes = [axes] if len(specs) == 1 else list(axes)
    for ax, spec in zip(axes, specs):
        parts = spec.split(":")
        var, title = parts[0], parts[1] if len(parts) > 1 else parts[0]
        k = float(parts[2]) if len(parts) > 2 else 1.0
        g = {p: [float(r[f"{var}|{p}"]) * k for r in rows] for p in ("P5", "P25", "P50", "P75", "P95")}
        ax.set_facecolor(SURFACE)
        ax.fill_between(t, g["P5"], g["P95"], color=OUTER, linewidth=0)
        ax.fill_between(t, g["P25"], g["P75"], color=INNER, linewidth=0)
        ax.plot(t, g["P50"], color=MEDIAN, linewidth=2)
        x = t[-1]
        for p, lab, dy in (("P95", "P95", 0), ("P75", "P75", 0), ("P50", "median", 0), ("P25", "P25", 0), ("P5", "P5", 0)):
            ax.annotate(f"{lab} {number(g[p][-1])}" if k == 1 else f"{lab} {number(g[p][-1])}%", (x, g[p][-1]),
                        xytext=(4, dy), textcoords="offset points", va="center", fontsize=7.5, color=INK2)
        ax.set_title(title, loc="left", fontsize=10, color=INK)
        ax.set_xlabel(time_label(src), fontsize=8.5, color=INK2)
        ax.grid(axis="y", color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(GRID)
        ax.tick_params(colors=INK2, labelsize=8)
        ax.set_xlim(t[0], t[-1])
        ax.set_ylim(bottom=0)
    fig.text(0.01, 0.005, "Bands: P5-P95 (light) and P25-P75 (dark) across 1,000 Latin hypercube runs; line = median. "
             "Not a forecast.", fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.04, 0.97, 1))
    fig.savefig(out, facecolor=SURFACE)


if __name__ == "__main__":
    main(sys.argv[1:])
