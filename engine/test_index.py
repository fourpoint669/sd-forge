"""Retrieval test for INDEX.md: for each sample topic, simulate an agent following INDEX.md.

Usage:  python -I engine/test_index.py
Read 1 = INDEX.md (row for the topic). Read 2 = the 'read first' library file (anchor must exist).
Read 3 = a listed model file (must exist). PASS = material (equations and, where available, a model) reached in <= 3 reads.
"""
import os
import re
import sys

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(root)
index = open("INDEX.md").read()
TOPICS = ["Bass diffusion", "SIR", "Shifting the burden", "Supply chain", "World3"]
ok_all = True
for t in TOPICS:
    reads, notes = 1, []
    row = next((l for l in index.splitlines() if l.startswith("|") and l.split("|")[1].strip().startswith(t)), None)
    if row is None:
        print(f"FAIL {t}: no INDEX row"); ok_all = False; continue
    cells = [c.strip() for c in row.split("|")[1:-1]]
    ref = re.search(r"`([^`#]+)(?:#([^`]+))?`", cells[1])
    path, anchor = ref.group(1), ref.group(2)
    reads += 1
    text = open(path).read() if os.path.exists(path) else ""
    heads = {re.sub(r"[^a-z0-9 -]", "", h.lower()).strip().replace(" ", "-") for h in re.findall(r"^#+\s*(.+)$", text, re.M)}
    # GitHub-style slug: lowercase, drop punctuation, spaces->hyphens ('&'/'+' vanish leaving '--')
    heads |= {re.sub(r"[^a-z0-9 -]", "", h.lower()).replace(" ", "-") for h in re.findall(r"^#+\s*(.+)$", text, re.M)}
    anchor_ok = anchor is None or anchor in heads
    models = re.findall(r"`(raw/[^`]+)`", cells[2])
    model_ok = bool(models) and os.path.exists(models[0])
    if models:
        reads += 1
    ok = bool(text) and anchor_ok and reads <= 3 and (model_ok or not models)
    print(f"{'PASS' if ok else 'FAIL'} {t}: reads={reads} library={path}{'#'+anchor if anchor else ''} anchor_ok={anchor_ok} model={'%s' % models[0] if models else 'NONE in raw/ (equations only)'}")
    ok_all &= ok
sys.exit(0 if ok_all else 1)
