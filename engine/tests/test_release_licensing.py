"""Licensing rules for publishing the repository: licence files, third-party notices, removed upstreams,
no foreign copyright lines inside the vendored raw/ files, no dangling raw/ paths, no stale README claims."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REMOVED = ["raw/pyworld3", "raw/worlddynamics-jl",
           "raw/sdeverywhere/models/invertmatrixio", "raw/sdeverywhere/models/sir"]
LICENCE_NAMES = ("LICENSE", "LICENSE.md")


def _tracked(*pathspec):
    out = subprocess.run(["git", "ls-files", "-z", *pathspec], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\0") if p]


def _raw_folders():
    return sorted(p.name for p in (ROOT / "raw").iterdir() if p.is_dir() and p.name != "_private")


def _raw_text_files():
    """Tracked text files under raw/ except the upstream LICENSE* and AUTHORS files themselves."""
    files = []
    for rel in _tracked("raw"):
        name = Path(rel).name
        if name.startswith("LICENSE") or name == "AUTHORS":
            continue
        data = (ROOT / rel).read_bytes()
        if b"\0" in data[:4096]:
            continue                                   # binary: spreadsheets, .mky and the like
        files.append(ROOT / rel)
    return files


def test_root_licence_files():
    lic = (ROOT / "LICENSE").read_text()
    assert lic.lstrip().startswith("Apache License")
    assert "Version 2.0, January 2004" in lic
    notice = (ROOT / "NOTICE").read_text()
    assert "sd-forge" in notice and "Apache License, Version 2.0" in notice
    assert (ROOT / "THIRD_PARTY_LICENSES.md").is_file()


def test_every_raw_folder_has_its_licence_file():
    missing = [d for d in _raw_folders() if not any((ROOT / "raw" / d / n).is_file() for n in LICENCE_NAMES)]
    assert missing == []


def test_every_raw_folder_is_listed_in_third_party_licenses():
    text = (ROOT / "THIRD_PARTY_LICENSES.md").read_text()
    folders = _raw_folders()
    assert [d for d in folders if f"`raw/{d}/`" not in text] == []
    listed = set(re.findall(r"`raw/([^/`]+)/`", text))
    assert sorted(listed - set(folders)) == []


def test_removed_upstreams_are_gone():
    assert [p for p in REMOVED if (ROOT / p).exists()] == []
    for table in ("MANIFEST.csv", "engine/translation_report.csv"):
        stale = [ln for ln in (ROOT / table).read_text().splitlines() if ln.startswith(tuple(p + "/" for p in REMOVED))]
        assert stale == [], table


def test_no_foreign_copyright_notice_in_raw():
    pattern = re.compile(r"©|\(c\)\s*\d{4}|copyright|all rights reserved", re.I)
    hits = [str(f.relative_to(ROOT)) for f in _raw_text_files()
            if pattern.search(f.read_text(encoding="utf-8", errors="ignore"))]
    assert hits == []


def test_no_dangling_raw_paths():
    docs = ["INDEX.md", *_tracked("library"), *_tracked("docs/src")]
    on_disk = set(_tracked("raw"))
    problems = []
    for rel in docs:
        if not rel.endswith(".md"):
            continue
        for path in re.findall(r"`(raw/[^`]+)`", (ROOT / rel).read_text(errors="ignore")):
            if any(ch in path for ch in "<*{") or "..." in path or "_private" in path:
                continue
            p = path.rstrip("/")
            if p not in on_disk and not any(f.startswith(p + "/") for f in on_disk):
                problems.append(f"{rel}: {path}")
    assert problems == []


def test_readme_does_not_say_private():
    for rel in ("README.md", "docs/src/README.md"):
        assert "repository is private" not in (ROOT / rel).read_text(), rel


def test_share_alike_sentence_is_current():
    manifest = (ROOT / "MANIFEST.csv").read_text().splitlines()
    assert [ln for ln in manifest if ln.startswith("raw/") and ",share-alike," in ln] == []
    assert "currently `raw/pyworld3`" not in (ROOT / "docs/src/README.md").read_text()
