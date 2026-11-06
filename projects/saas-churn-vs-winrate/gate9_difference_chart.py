"""Per-sample difference chart for gate 9: ARR of win rate first minus churn first (equal 30/30 split), P5-P95 and
P25-P75 bands across the 1,000 samples, plain-dollar labels, zero line. Same visual style as engine/fan_chart.py,
but the y-axis is not clamped at 0 (a difference can be negative). Refuses to draw unless validate.py and checks.py
both passed.

    .venv/bin/python -I projects/saas-churn-vs-winrate/gate9_difference_chart.py
"""
import csv
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
OUTER, INNER, MEDIAN = "#b7d3f6", "#6da7ec", "#1c5cab"
VAR = "win rate first minus churn first (30/30)|ARR"


def passed(name):
    try:
        return json.load(open(os.path.join(HERE, name))).get("all_pass") is True
    except (OSError, ValueError):
        return False


def dollars(x, _=None):
    return f"-${abs(x):,.0f}" if x < 0 else f"${x:,.0f}"


def main():
    if not (passed("validation_results.json") and passed("checks_results.json")):
        sys.exit("refusing to draw: validate.py or checks.py has not passed")
    rows = list(csv.DictReader(open(os.path.join(HERE, "order_difference_bands.csv"))))
    t = [float(r["time"]) for r in rows]
    g = {p: [float(r[f"{VAR}|{p}"]) for r in rows] for p in ("P5", "P25", "P50", "P75", "P95")}
    share = [float(r["share_win_first_ahead"]) for r in rows]
    # the statistics quoted in summary.md, computed from order_difference_bands.csv and written next to it
    ipk = max(range(len(t)), key=lambda k: g["P50"][k])
    after = range(ipk + 1, len(t))
    stats = {"source": "order_difference_bands.csv (monthly rows; difference = win rate first minus churn first, 30/30, ARR USD/yr)",
             "median_peak": {"month": t[ipk], "value": g["P50"][ipk]},
             "median_first_month_at_or_below_zero_after_peak": next((t[k] for k in after if g["P50"][k] <= 0), None),
             "share_win_first_first_month_below_half_after_peak": next((t[k] for k in after if share[k] < 0.5), None),
             "at_month": {str(int(m)): {p: g[p][t.index(m)] for p in ("P5", "P25", "P50", "P75", "P95")}
                          | {"share_win_first_ahead": share[t.index(m)]} for m in (36.0, 60.0, 120.0)}}
    json.dump(stats, open(os.path.join(HERE, "order_difference_summary.json"), "w"), indent=1)
    fig, ax = plt.subplots(figsize=(8.6, 4.2), dpi=150, facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    ax.fill_between(t, g["P5"], g["P95"], color=OUTER, linewidth=0)
    ax.fill_between(t, g["P25"], g["P75"], color=INNER, linewidth=0)
    ax.plot(t, g["P50"], color=MEDIAN, linewidth=2)
    ax.axhline(0, color=INK, linewidth=0.9)
    ax.axvline(60, color=INK2, linewidth=0.8, linestyle=(0, (3, 3)))
    i60 = t.index(60.0)
    ax.annotate(f"month 60: win rate first ahead in {share[i60] * 1000:.0f} of 1,000", (60, ax.get_ylim()[1]),
                xytext=(4, -12), textcoords="offset points", fontsize=7.5, color=INK2)
    for p, lab in (("P95", "P95"), ("P75", "P75"), ("P50", "median"), ("P25", "P25"), ("P5", "P5")):
        ax.annotate(f"{lab} {dollars(g[p][-1])}", (t[-1], g[p][-1]), xytext=(4, 0), textcoords="offset points",
                    va="center", fontsize=7.5, color=INK2)
    ax.yaxis.set_major_formatter(FuncFormatter(dollars))
    ax.set_title("ARR difference per sample: win rate first minus churn first (equal 30/30 split), USD per year",
                 loc="left", fontsize=9.5, color=INK)
    ax.set_xlabel("Months since launch", fontsize=8.5, color=INK2)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.set_xlim(t[0], t[-1])
    fig.text(0.01, 0.01, "Above zero: win rate first has higher ARR in that sample. Bands: P5-P95 (light), P25-P75 (dark)\n"
             "of the per-sample difference across 1,000 Latin hypercube samples; line = median. Not a forecast.",
             fontsize=7, color=INK2)
    fig.tight_layout(rect=(0, 0.07, 0.86, 1))
    fig.savefig(os.path.join(HERE, "difference_chart.png"), facecolor=SURFACE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
