"""/sd-explorer skill and command, and gate 10 in /sd-model: files exist, every command and file they name exists,
and they state the tested scope."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL = os.path.join(ROOT, ".claude", "skills", "sd-explorer", "SKILL.md")
CMD = os.path.join(ROOT, ".claude", "commands", "sd-explorer.md")
MODEL_SKILL = os.path.join(ROOT, ".claude", "skills", "sd-model", "SKILL.md")
MODEL_CMD = os.path.join(ROOT, ".claude", "commands", "sd-model.md")


def _read(p):
    return open(p, encoding="utf-8").read()


def test_frontmatter_triggers_only():
    s = _read(SKILL)
    m = re.match(r"---\nname: sd-explorer\ndescription: (Use when [^\n]+)\n---\n", s)
    assert m and len(m.group(1)) < 500
    assert "gate 10" in m.group(1)


def test_every_engine_file_and_command_named_exists():
    for p in (SKILL, CMD, MODEL_SKILL):
        for f in set(re.findall(r"engine/[\w/.-]+", _read(p))):
            assert os.path.exists(os.path.join(ROOT, f.rstrip("/."))), (p, f)


def test_skill_states_scope_and_loud_failure():
    s = _read(SKILL)
    assert "two projects of the same model family" in s and "fails the build loudly" in s
    assert "--mode unattended" in s and "Never wait for an answer" in s and "Never require a plugin" in s
    assert "up to 4 questions" in s and "skip = default" in s


def test_sd_model_has_gate_10_after_gate_9():
    s = _read(MODEL_SKILL)
    assert "Ten gates" in s and "Nine gates" not in s
    rows = [l for l in s.splitlines() if re.match(r"\| (9|10) ", l)]
    assert [r.split("|")[1].strip()[:2] for r in rows] == ["9 ", "10"]
    assert "Only after gate 9 is approved" in rows[1] and "check_repo.py --require-explorer" in rows[1]
    c = _read(MODEL_CMD)
    assert "10 gates" in c and "9 gates" not in c
