"""Translate and run every .mdl/.xmile/.stmx model with PySD and write a report.

Usage:  python -I engine/translate_all.py <report.csv> <dir-or-file> [<dir-or-file> ...]

Each model runs in a separate worker process (timeout-bounded) on a copy of its
directory in a temp dir, so PySD's generated .py never lands in raw/.
"""
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import warnings
from concurrent.futures import ThreadPoolExecutor

TIMEOUT_S = 90
MODEL_EXT = {".mdl": "vensim", ".xmile": "xmile", ".stmx": "xmile", ".itmx": "xmile"}
COLUMNS = ["model_path", "format", "translates", "runs", "runtime_s",
           "unsupported_functions", "error", "pysd_version"]


def worker(path):
    """Child-process entry point: print one JSON result line."""
    import pysd
    ext = os.path.splitext(path)[1].lower()
    out = {"translates": False, "runs": False, "unsupported": [], "error": "",
           "pysd_version": pysd.__version__}
    src_dir = os.path.dirname(os.path.abspath(path))
    with tempfile.TemporaryDirectory() as tmp:
        for f in os.listdir(src_dir):
            p = os.path.join(src_dir, f)
            if os.path.isfile(p):
                shutil.copy2(p, tmp)
        model_file = os.path.join(tmp, os.path.basename(path))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                reader = pysd.read_vensim if ext == ".mdl" else pysd.read_xmile
                model = reader(model_file)
                out["translates"] = True
                try:
                    model.run()
                except ValueError as e:
                    # Vensim "data" variables need their .tab files passed explicitly
                    if "before loading the data" not in str(e):
                        raise
                    tabs = sorted(os.path.join(tmp, f) for f in os.listdir(tmp) if f.lower().endswith(".tab"))
                    model = reader(model_file, data_files=tabs)
                    model.run()
                    out["data_files_retry"] = True
                out["runs"] = True
            except BaseException as e:  # noqa: BLE001 - report everything
                out["error"] = f"{type(e).__name__}: {e}"[:400].replace("\n", " ")
        msgs = [str(w.message) for w in caught] + [out["error"]]
    names = set()
    for m in msgs:
        for pat in (r"[Nn]ot implemented function ['\"`]([^'\"`]+)['\"`]",
                    r"[Uu]nsupported function ['\"`]([^'\"`]+)['\"`]",
                    r"function ['\"`]([A-Za-z_][\w ]*)['\"`] (?:is )?not"):
            names.update(x.strip().lower() for x in re.findall(pat, m))
    out["unsupported"] = sorted(names)[:8]
    print("RESULT" + json.dumps(out))


def run_one(path):
    ext = os.path.splitext(path)[1].lower()
    row = {"model_path": path, "format": MODEL_EXT[ext], "translates": False, "runs": False,
           "runtime_s": 0.0, "unsupported_functions": "", "error": "", "pysd_version": ""}
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, "-I", os.path.abspath(__file__), "--worker", path],
                           capture_output=True, text=True, timeout=TIMEOUT_S)
        line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT")), None)
        if line is None:
            row["error"] = ("worker crashed: " + p.stderr.strip().splitlines()[-1])[:400] if p.stderr.strip() else "worker crashed"
        else:
            r = json.loads(line[6:])
            row.update(translates=r["translates"], runs=r["runs"], error=r["error"],
                       unsupported_functions=";".join(r["unsupported"]), pysd_version=r["pysd_version"])
    except subprocess.TimeoutExpired:
        row["error"] = f"timeout after {TIMEOUT_S}s"
    row["runtime_s"] = round(time.time() - t0, 2)
    return row


def main(argv):
    report, targets = argv[0], argv[1:]
    models = []
    for t in targets:
        if os.path.isfile(t):
            models.append(t)
            continue
        for dp, _, fn in os.walk(t):
            models += [os.path.join(dp, f) for f in fn if os.path.splitext(f)[1].lower() in MODEL_EXT]
    models = sorted(set(models))
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as ex:
        rows = list(ex.map(run_one, models))
    with open(report, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    n = len(rows)
    print(f"{n} models: {sum(r['translates'] for r in rows)} translate, {sum(r['runs'] for r in rows)} run")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--worker":
        worker(sys.argv[2])
    else:
        main(sys.argv[1:])
