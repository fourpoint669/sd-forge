"""Fan chart for car-dealership-profit: same palette and layout as engine/fan_chart.py, but the y-axis is not forced to start
at 0, because cumulative and monthly profit go negative (the engine script clips at 0 and would hide the losses).
Refuses to draw unless validation_results.json says all_pass, like the engine script.

    .venv/bin/python -I projects/car-dealership-profit/gate9_fan_chart.py
"""
import csv
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
WRITES = ("fan_chart.png",)
READS = ("mc_bands.csv",)
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import fan_chart as fc  # noqa: E402

PANELS = [("Cumulative Net Profit", "Cumulative net profit before tax (USD million)", 1e-6, "{:,.1f}"),
          ("net profit", "Monthly net profit before tax (USD thousand per month)", 1e-3, "{:,.0f}"),
          ("Service Customers", "Service customers (households)", 1.0, "{:,.0f}")]


def main():
    src = os.path.join(HERE, "mc_bands.csv")
    if not fc.validated(src):
        sys.exit("refusing to draw: validation has not passed")
    rows = list(csv.DictReader(open(src)))
    t = [float(r["time"]) for r in rows]
    fig, axes = plt.subplots(1, len(PANELS), figsize=(5.4 * len(PANELS), 3.7), dpi=150, facecolor=fc.SURFACE)
    for ax, (var, title, k, fmt) in zip(axes, PANELS):
        g = {p: [float(r[f"{var}|{p}"]) * k for r in rows] for p in ("P5", "P25", "P50", "P75", "P95")}
        ax.set_facecolor(fc.SURFACE)
        ax.fill_between(t, g["P5"], g["P95"], color=fc.OUTER, linewidth=0)
        ax.fill_between(t, g["P25"], g["P75"], color=fc.INNER, linewidth=0)
        ax.plot(t, g["P50"], color=fc.MEDIAN, linewidth=2)
        if min(g["P5"]) < 0:
            ax.axhline(0, color=fc.INK2, linewidth=0.8)
        # end labels, nudged apart so P5 and P25 do not overlap
        ends = sorted([(g[p][-1], lab) for p, lab in (("P95", "P95"), ("P75", "P75"), ("P50", "median"), ("P25", "P25"), ("P5", "P5"))])
        span = (max(g["P95"]) - min(g["P5"])) or 1.0
        placed = []
        for y, lab in ends:
            yy = y if not placed or y - placed[-1] > 0.055 * span else placed[-1] + 0.055 * span
            placed.append(yy)
            ax.annotate(f"{lab} {fmt.format(y)}", (t[-1], y), xytext=(4, 0), textcoords="offset points", va="center", fontsize=7.5, color=fc.INK2)
        ax.set_title(title, loc="left", fontsize=10, color=fc.INK)
        ax.set_xlabel("Months from today", fontsize=8.5, color=fc.INK2)
        ax.grid(axis="y", color=fc.GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(fc.GRID)
        ax.tick_params(colors=fc.INK2, labelsize=8)
        ax.set_xlim(t[0], t[-1])
    fig.text(0.01, 0.005, "Baseline store, no lever change. Bands: P5-P95 (light) and P25-P75 (dark) across 1,000 Latin hypercube runs; "
             "line = median. The spread is mostly uncertainty about the store's own economics. Not a forecast.", fontsize=7.5, color=fc.INK2)
    fig.tight_layout(rect=(0, 0.04, 0.95, 1))
    fig.savefig(os.path.join(HERE, "fan_chart.png"), facecolor=fc.SURFACE)


if __name__ == "__main__":
    main()
