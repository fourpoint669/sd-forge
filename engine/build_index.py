"""Generate INDEX.md from MANIFEST.csv + engine/translation_report.csv.

Usage:
  python -I engine/build_index.py            write INDEX.md
  python -I engine/build_index.py --check     print how a fresh build differs from the committed INDEX.md and exit 1
                                              if it does; writes nothing

The committed INDEX.md carries hand edits that this script does not reproduce (see the "Repository layout and
rerun" section of docs/MANUAL.md), so --check is expected to report a difference. Use it to see whether that
difference is only the hand edits before overwriting them.
"""
import collections
import csv
import difflib
import glob
import json
import os
import sys

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(root)
man = list(csv.DictReader(open("MANIFEST.csv")))
rep = {r["model_path"]: r for r in csv.DictReader(open("engine/translation_report.csv"))}

def status(p):
    r = rep.get(p)
    if not r:
        return "n/a" if p.endswith(".mky") else "-"
    return "runs" if r["runs"] == "True" else "translates-only" if r["translates"] == "True" else "fails"

models = [m for m in man if m["type"] in ("model", "code") and m["path"].startswith("raw/")]
tagmap = collections.defaultdict(list)
for m in models:
    for t in m["domain_tags"].split(";"):
        if t:
            tagmap[t].append(m)

out = ["# INDEX", "",
       "Route: **topic -> table below -> file**. Read order for an agent: (1) this file, (2) the `library/` file named for the topic, (3) the model path listed (full row detail: `MANIFEST.csv`; status detail: `engine/translation_report.csv`).",
       "Status: `runs` = PySD translated and ran; `translates-only` = translated, run failed; `fails` = translation failed; `n/a` = format PySD cannot read.",
       "", "## Topic routing", "",
       "| Topic | Read first | Models (best first; up to 5) |", "|---|---|---|"]
topics = [
 ("Bass diffusion / adoption", "library/archetypes.md#4-bass-diffusion-r--b-adoption", ["adoption"]),
 ("SIR / epidemic / contagion", "library/archetypes.md#5-sir-epidemic-r--b", ["epidemiology"]),
 ("Shifting the burden", "library/archetypes.md#7-shifting-the-burden-b--b--r", ["shifting-the-burden"]),
 ("Supply chain / inventory / beer game", "library/archetypes.md#6-stock-management-with-delay-b-with-delay", ["supply-chain"]),
 ("World3 / limits to growth", "library/notes/limits-to-growth-world3.md", ["world-dynamics"]),
 ("Resource depletion / overshoot", "library/archetypes.md#8-resource-depletion-overshoot-and-collapse", ["resource-depletion"]),
 ("Pricing / competition", "library/archetypes.md#9-market-growth--capacity-r--b-with-delay", ["pricing"]),
 ("Churn / customer acquisition", "library/archetypes.md#9-market-growth--capacity-r--b-with-delay", ["churn-customers"]),
 ("Market growth / capacity", "library/archetypes.md#9-market-growth--capacity-r--b-with-delay", ["market-growth", "capacity"]),
 ("Energy / climate", "library/archetypes.md", ["energy-climate"]),
 ("Goal seeking (teacup)", "library/archetypes.md#2-goal-seeking-b", ["goal-seeking"]),
 ("Predator-prey / population", "library/archetypes.md", ["population"]),
]
rank = {"runs": 0, "translates-only": 1, "n/a": 2, "fails": 3, "-": 4}
for name, read, tags in topics:
    cands = {m["path"]: m for t in tags for m in tagmap.get(t, [])}
    # prefer runnable, tier A, and one file per model family (mdl before xmile/stmx)
    seen, picks = set(), []
    for m in sorted(cands.values(), key=lambda m: (rank[status(m["path"])], m["quality_tier"], m["path"].endswith((".xmile", ".stmx")), m["path"])):
        fam = os.path.splitext(m["path"])[0].rsplit("/", 1)[0] + "/" + os.path.basename(m["path"]).split(".")[0]
        if fam in seen:
            continue
        seen.add(fam); picks.append(m)
        if len(picks) == 5:
            break
    cell = "<br>".join(f"`{m['path']}` ({m['quality_tier']}, {status(m['path'])})" for m in picks) or "none yet"
    out.append(f"| {name} | `{read}` | {cell} | ".rstrip() )
out += ["", "## Validated projects (built with /sd-model)", "",
        "| Project | Question / title | Validation | Read first | Explorer |", "|---|---|---|---|---|"]
projects = sorted(glob.glob("projects/*/"))
for d in projects:
    summ = os.path.join(d, "summary.md")
    title = next((l.lstrip("# ").strip() for l in open(summ) if l.startswith("# ")), d) if os.path.exists(summ) else d
    try:
        ok = "all tests pass" if json.load(open(os.path.join(d, "validation_results.json"))).get("all_pass") else "FAILING"
    except (OSError, ValueError):
        ok = "not validated"
    page = os.path.join(d, "explorer.html")
    out.append(f"| `{d.rstrip('/')}` | {title} | {ok} | `{summ}` | " + (f"`{page}` |" if os.path.exists(page) else "not built (/sd-explorer) |"))
if not projects:
    out.append("| none yet | | | | |")
out += ["", "## Library files", "",
        "| File | Content |", "|---|---|",
        "| `library/archetypes.md` | archetype catalog: structure, polarity, behavior, equations |",
        "| `library/units.md` | unit conventions |",
        "| `library/function_compatibility.md` | Vensim function vs PySD support (from translation report) |",
        "| `library/modeling_checklist.md` | modeling process |",
        "| `library/validation_tests.md` | tests T1-T7 with numeric tolerances |",
        "| `library/notes/` | chapter-level notes for books/papers (pointers only) |", "",
        "## Sources", "", "| Source folder | License | commercial_use | Tier | Models | Run OK |", "|---|---|---|---|---|---|"]
bysrc = collections.OrderedDict()
for m in man:
    if m["path"].startswith("raw/"):
        bysrc.setdefault(m["path"].split("/")[1], []).append(m)
for s, ms in bysrc.items():
    mod = [m for m in ms if m["type"] == "model" and m["path"].lower().endswith((".mdl", ".xmile", ".stmx"))]
    ok = sum(status(m["path"]) == "runs" for m in mod)
    out.append(f"| `raw/{s}/` | {ms[0]['license']} | {ms[0]['commercial_use']} | {ms[0]['quality_tier']} | {len(mod) or len([m for m in ms if m['type']=='model'])} | {ok}/{len(mod)} |" if mod else
               f"| `raw/{s}/` | {ms[0]['license']} | {ms[0]['commercial_use']} | {ms[0]['quality_tier']} | {len([m for m in ms if m['type'] in ('model','code')])} files | n/a |")
out += ["", "## Pointer-only items (no content stored)", ""]
for m in man:
    if m["path"].startswith("pointer:"):
        out.append(f"- `{m['path']}` — {m['license']}; commercial_use={m['commercial_use']}; {m['source_url']}")
out += ["", "Sources that were not downloaded are `pointer:` rows in `MANIFEST.csv`.", ""]
fresh = "\n".join(out)
committed = open("INDEX.md", encoding="utf-8").read() if os.path.exists("INDEX.md") else None

if "--check" in sys.argv[1:]:
    if committed == fresh:
        print("INDEX.md matches a fresh build")
        sys.exit(0)
    print("INDEX.md differs from a fresh build; nothing was written. The committed file carries hand edits this "
          "script does not reproduce, so a difference is expected: check that it is only those edits.")
    if committed is not None:
        diff = list(difflib.unified_diff(committed.splitlines(), fresh.splitlines(),
                                         "committed INDEX.md", "fresh build", lineterm=""))
        print("\n".join(diff[:80]))
        if len(diff) > 80:
            print(f"... {len(diff) - 80} more diff lines")
    sys.exit(1)

open("INDEX.md", "w").write(fresh)
print("INDEX.md written")
