"""Run modes of /sd-model: where the pipeline pauses for a person, and how a project built without every pause says so.

  python -I engine/run_mode.py label MODE      print the line summary.md must open with (checkpoint and express)
  python -I engine/run_mode.py check DIR       print the problems with the project's run-mode records (exit 1 if any)

Modes (PAUSES; the table in .claude/skills/sd-model/SKILL.md is checked against it):
  full         pause after every gate, 1 to 10 (the original behaviour)
  checkpoint   pause once after gate 5 (assumptions register and validation.toml), and once at the end
  express      no pauses
Hard rules in every mode (not code here, stated in the skill and kept by validate.py and explorer_release.py):
gate 1 refuses a question that names no decision; a gate 7 failure stops the run; the explorer refusal gates and
every tolerance are unchanged.

Records. A project built in checkpoint or express mode (project_problems, run by engine/check_repo.py):
  - every gate file (RECORDS) carries '**Run mode:** <mode>' and '**Approval:** self-approved|person-approved'
    (validation.toml: the same two lines as '# ' comments), each equal to what the mode allows (APPROVAL);
  - assumptions_register.md tags every 'estimated' parameter '[assumed]' in its Confidence cell;
  - summary.md opens, right after its title, with the mode's label line (LABELS), which the explorer repeats at the
    top of its Model limits dialog; an express page also shows it as a banner (page_problems).
A project with no run-mode record is a full-mode project built before modes existed; nothing more is required of it.
Limit: this checks that the records exist and agree with each other; it cannot know whether an Approval line is true.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sd_paths  # noqa: E402

MODES = ("full", "checkpoint", "express")
DEFAULT = "checkpoint"
GATES = tuple(range(1, 11))
END = "end"
PAUSES = {"full": [(g, f"after gate {g}") for g in GATES],
          "checkpoint": [(5, "after gate 5, to review assumptions_register.md and validation.toml"), (END, "at the end, after gate 10")],
          "express": []}
# gate files that carry the record, per gate
RECORDS = {1: ["01_problem.md"], 2: ["02_boundary.md"], 3: ["03_dynamic_hypothesis.md"], 4: ["04_stock_flow.md"],
           5: ["assumptions_register.md", "validation.toml"], 8: ["08_policy.md"]}
SELF, PERSON = "self-approved", "person-approved"
APPROVAL = {"checkpoint": {g: (PERSON if g == 5 else SELF) for g in RECORDS},
            "express": {g: SELF for g in RECORDS}}
ASSUMED = "[assumed]"
LABELS = {
    "checkpoint": ("**Not reviewed by a person:** built in checkpoint mode. A person reviewed the assumptions register and "
                   "validation.toml (gate 5); the problem, boundary, loops, stock-flow structure (gates 1-4), the "
                   "implementation, validation run, policy scenarios and this summary (gates 6-10) were self-approved by "
                   "the builder, an AI agent, and had not been reviewed by a person when this line was written."),
    "express": ("**Not reviewed by a person:** built in express mode. No person reviewed any gate: the problem, boundary, "
                "loops, stock-flow structure, assumptions register, validation.toml, implementation, policy scenarios "
                "and summary were all self-approved by the builder, an AI agent."),
}
BANNER_CLASS = "run-mode-banner"
_MODE = re.compile(r"^(?:#\s*|\*\*)Run mode:?(?:\*\*)?\s*(\S+)", re.M)
_APPR = re.compile(r"^(?:#\s*|\*\*)Approval:?(?:\*\*)?\s*([\w-]+)", re.M)


def stops(mode):
    """The pauses of a mode as gate numbers (and END)."""
    return [g for g, _ in PAUSES[mode]]


def label(mode):
    return LABELS.get(mode)


def _read(project_dir, rel):
    p = os.path.join(project_dir, rel)
    return open(p, encoding="utf-8").read() if os.path.exists(p) else None


STAMPED_RECORDS = ("assumptions_register.md", "validation.toml")      # the record files the explorer release stamp covers


def declared(project_dir, only=None):
    """{file: (mode or None, approval or None)} for every record file that exists (only: just those named)."""
    out = {}
    for g, files in RECORDS.items():
        for f in files:
            if only is not None and f not in only:
                continue
            t = _read(project_dir, f)
            if t is not None:
                m, a = _MODE.search(t), _APPR.search(t)
                out[f] = (m.group(1).strip("*") if m else None, a.group(1) if a else None)
    return out


def read_mode(project_dir, only=None):
    """('full'|'checkpoint'|'express', problems). The riskiest mode any record declares wins, so deleting the line from
    one file cannot turn an express project into a full one; no record at all means a full-mode project."""
    found = declared(project_dir, only)
    seen = {m for m, _ in found.values() if m}
    bad = sorted(s for s in seen if s not in MODES)
    probs = [f"unknown run mode '{b}' (use one of {', '.join(MODES)})" for b in bad]
    seen -= set(bad)
    if len(seen) > 1:
        probs.append(f"gate files declare different run modes: {sorted(seen)}")
    mode = "express" if "express" in seen else "checkpoint" if "checkpoint" in seen else "full"
    return mode, probs


def _confidence_rows(text):
    """(parameter cell, confidence cell) for every register table row that has a Confidence column."""
    lines, i, out = text.splitlines(), 0, []
    cells = lambda l: [c.strip() for c in l.strip().strip("|").split("|")]  # noqa: E731
    while i < len(lines) - 1:
        if lines[i].lstrip().startswith("|") and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            head = [h.lower() for h in cells(lines[i])]
            i += 2
            if "confidence" in head:
                ci, ni = head.index("confidence"), 0
                while i < len(lines) and lines[i].lstrip().startswith("|"):
                    c = cells(lines[i])
                    if len(c) > ci:
                        out.append((c[ni], c[ci]))
                    i += 1
            continue
        i += 1
    return out


def project_problems(project_dir):
    """Problems with a project's run-mode records; [] for a full-mode project."""
    mode, probs = read_mode(project_dir)
    if mode == "full":
        return probs
    found = declared(project_dir)
    for g, files in RECORDS.items():
        for f in files:
            if f not in found:
                continue                        # a missing gate file is reported by check_repo
            m, a = found[f]
            if m != mode:
                probs.append(f"{f} does not record 'Run mode: {mode}'")
            want = APPROVAL[mode][g]
            if a != want:
                probs.append(f"{f} records Approval '{a}', {mode} mode needs '{want}'")
    reg = _read(project_dir, "assumptions_register.md")
    if reg is not None:
        for name, conf in _confidence_rows(reg):
            if re.sub(r"[*_`\s]", "", conf).lower().startswith("estimated") and ASSUMED not in conf:
                probs.append(f"assumptions_register.md: estimated parameter '{name}' is not tagged {ASSUMED}")
    summ = _read(project_dir, "summary.md")
    if summ is not None:
        body = [l for l in summ.splitlines()[1:] if l.strip()]
        if not body or body[0].strip() != LABELS[mode]:
            probs.append(f"summary.md must open (right after the title) with the {mode}-mode line: "
                         "python -I engine/run_mode.py label " + mode)
    return probs


def limits_with_label(limits, mode):
    """The summary's Model limits text with the mode's line right under its heading (unchanged for full mode)."""
    if mode == "full":
        return limits
    head, _, rest = limits.partition("\n")
    return head + "\n\n" + LABELS[mode] + "\n" + (rest if rest.startswith("\n") else "\n" + rest)


def banner_html(mode):
    """The express banner, inline-styled so the page template (and every older page's stamp) stays as it is."""
    if mode != "express":
        return ""
    text = LABELS[mode].replace("**", "").replace("&", "&amp;").replace("<", "&lt;")
    return (f'<div class="{BANNER_CLASS}" role="note" style="background:#fff3cd;color:#3b2a00;border-bottom:2px solid #8a6100;'
            f'padding:8px 16px;font:600 14px/1.4 system-ui,sans-serif">{text}</div>\n')


def page_problems(project_dir, data, html):
    """For a shipped page: it was built in the project's current mode, carries the label in its Model limits, and an
    express page shows the banner. `data` is the page's sd-data; a page built before modes has no run_mode (full)."""
    mode, _ = read_mode(project_dir)
    built = (data.get("run_mode") or {}).get("mode", "full")
    if built != mode:
        return [f"the page was built in {built} mode but the project records {mode} (rebuild it)"]
    probs = []
    if mode != "full" and LABELS[mode].replace("**", "") not in data.get("model_limits", "").replace("**", ""):
        probs.append(f"the page's Model limits do not carry the {mode}-mode line (rebuild it)")
    if mode == "express" and f'class="{BANNER_CLASS}"' not in html:
        probs.append("an express-mode page must show the not-reviewed banner (rebuild it)")
    return probs


def main(argv):
    if len(argv) == 3 and argv[1] == "label" and argv[2] in LABELS:
        print(LABELS[argv[2]])
        return 0
    argv, _ = sd_paths.extract_flag(argv)
    if len(argv) == 3 and argv[1] == "check":
        project = sd_paths.resolve_project(argv[2])
        problem = sd_paths.project_problem(project)
        if problem:                                           # nothing to check is an error, never "no problems"
            print("ERR", problem)
            return 1
        probs = project_problems(project)
        for p in probs:
            print("ERR", p)
        return 1 if probs else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
