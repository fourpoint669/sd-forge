"""Recompute domain_tags in MANIFEST.csv for model/code rows from the file path.

Usage:  python -I engine/retag_manifest.py
Keyword rules are deliberately narrow (whole-word) to avoid false topic hits such as
'fixed delay' -> shifting-the-burden or 'subscripts' -> churn.
"""
import csv
import os
import re

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(root)
TAGS = [
    (r"\bbass\b|diffusion|\badoption\b|innovator", "adoption"),
    (r"\bsir\b|\bseir\b|epidem|infect|covid", "epidemiology"),
    (r"inventory|supply.?chain|beer.?game|retailer|workforce|manufactur", "supply-chain"),
    (r"pricing|\bprice\b|competitive", "pricing"),
    (r"churn|customer|subscriber|acquisition|\bsaas\b", "churn-customers"),
    (r"predator|lotka|\bhares\b|lynx|\bprey\b|population", "population"),
    (r"world3|worldmodel|world_model|worlddynamics|meadows|limits.to.growth", "world-dynamics"),
    (r"resource|\bfish|depletion|renewable|forest", "resource-depletion"),
    (r"energy|\bco2\b|carbon|climate|\bghg\b", "energy-climate"),
    (r"\bmarket\b|saturat|logistic|s-?shaped", "market-growth"),
    (r"capacity|\bqueue\b|backlog", "capacity"),
    (r"teacup|cooling|goal.?seek", "goal-seeking"),
    (r"burden|addict", "shifting-the-burden"),
]
BASE = {"test-models": "pysd-test;function-test", "pysd": "pysd-test;function-test", "sdeverywhere": "sdeverywhere",
        "bptk-py": "bptk", "readsdr": "readsdr", "sdmr": "duggan-book", "simlin-stdlib": "simlin;stdlib"}
rows = list(csv.reader(open("MANIFEST.csv")))
hdr, body = rows[0], rows[1:]
ti = hdr.index("domain_tags")
for r in body:
    if r[0].startswith("raw/") and r[hdr.index("type")] in ("model", "code"):
        src = r[0].split("/")[1]
        rel = r[0].lower()
        tags = BASE.get(src, "").split(";") + [t for p, t in TAGS if re.search(p, rel)]
        r[ti] = ";".join(dict.fromkeys(t for t in tags if t))
with open("MANIFEST.csv", "w", newline="") as f:
    csv.writer(f).writerows([hdr] + body)
