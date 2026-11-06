"""The generators must not destroy committed hand edits, and must not rewrite files whose source did not change.

Two footguns this pins down. engine/build_index.py rewrites INDEX.md, whose committed copy carries hand edits the
script does not reproduce, so it needs a way to report a difference without overwriting it. And a PDF rendered from
an unchanged document is not byte-identical to the one already committed, so rebuilding all three on every
documentation change dirtied files whose text had not moved and forced their recorded hashes to be put back by hand.
"""
import hashlib
import json
import os
import subprocess
import sys

import build_docs as bd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _man():
    return json.load(open(os.path.join(ROOT, bd.PDF_MANIFEST), encoding="utf-8"))


# ------------------------------------------------------------------ build_docs --pdfs
def test_a_current_pdf_is_not_rebuilt():
    """The committed state: every document matches the PDF recorded for it, so nothing is stale."""
    assert bd.stale_pdfs(_man(), bd._pdf_sources()) == {}


def test_force_rebuilds_every_pdf():
    src = bd._pdf_sources()
    assert set(bd.stale_pdfs(_man(), src, force=True)) == set(src)


def test_a_missing_manifest_rebuilds_every_pdf():
    src = bd._pdf_sources()
    assert set(bd.stale_pdfs({}, src)) == set(src)
    assert set(bd.stale_pdfs({"documents": {}}, src)) == set(src)


def test_a_changed_document_rebuilds_only_its_own_pdf():
    man, src = _man(), bd._pdf_sources()
    man["documents"]["docs/MANUAL.md"]["source_sha256"] = "0" * 64
    assert set(bd.stale_pdfs(man, src)) == {"docs/MANUAL.md"}


def test_a_pdf_that_is_no_longer_the_recorded_file_is_rebuilt():
    man, src = _man(), bd._pdf_sources()
    man["documents"]["README.md"]["pdf_sha256"] = "0" * 64
    assert set(bd.stale_pdfs(man, src)) == {"README.md"}


def test_a_record_for_another_path_or_a_missing_record_rebuilds():
    man, src = _man(), bd._pdf_sources()
    man["documents"]["README.md"]["pdf"] = "docs/pdf/somewhere-else.pdf"
    del man["documents"]["docs/QUICKSTART.md"]
    assert set(bd.stale_pdfs(man, src)) == {"README.md", "docs/QUICKSTART.md"}


def test_a_missing_pdf_file_is_rebuilt():
    man, src = _man(), dict(bd._pdf_sources())
    src["docs/MANUAL.md"] = "docs/pdf/not-written-yet.pdf"
    assert "docs/MANUAL.md" in bd.stale_pdfs(man, src)


# ------------------------------------------------------------------ build_index --check
def test_build_index_check_never_writes_index_md():
    """--check reports how a fresh build differs and writes nothing. INDEX.md is the file this guards: running the
    generator to find out whether it had drifted used to be the way to lose its hand edits."""
    index = os.path.join(ROOT, "INDEX.md")
    before = hashlib.sha256(open(index, "rb").read()).hexdigest()
    r = subprocess.run([sys.executable, "-I", os.path.join("engine", "build_index.py"), "--check"],
                       cwd=ROOT, capture_output=True, text=True, timeout=300)
    after = hashlib.sha256(open(index, "rb").read()).hexdigest()
    assert after == before, "build_index.py --check rewrote INDEX.md"
    assert r.returncode in (0, 1), f"unexpected exit {r.returncode}: {r.stderr[-400:]}"
    assert "INDEX.md" in r.stdout
    if r.returncode == 1:
        assert "nothing was written" in r.stdout


def test_the_committed_index_still_carries_hand_edits():
    """Why --check exists: a fresh build does not reproduce the committed INDEX.md. If this ever fails, the hand
    edits are gone - either restore them or drop this test and the warning in docs/src/MANUAL.md with it."""
    r = subprocess.run([sys.executable, "-I", os.path.join("engine", "build_index.py"), "--check"],
                       cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert r.returncode == 1, "a fresh INDEX.md now matches the committed one"
    assert "hand edits" in r.stdout
