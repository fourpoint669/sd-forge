"""Intake for /sd-explorer: one round of up to 4 multiple-choice questions, every one skippable (skip = default).

Usage (every form takes --projects-root DIR; a bare <m> name is looked up under the projects root, engine/sd_paths.py):
  python -I engine/explorer_intake.py questions [projects/<m> ...]
      Prints the questions as JSON: [{id, header, question, options: [{key, label, description}], default}].
      With one project named, the decision question lists that project's metrics and presets. With none or several,
      the questions are generic and apply to every project built.
  python -I engine/explorer_intake.py record projects/<m> [--answers JSON] [--mode asked|unattended]
      Writes projects/<m>/explorer_intake.toml. JSON maps a question id to an option key; a missing id is a skipped
      question and takes the default. --mode unattended: nobody could be asked (all defaults).

The build reads explorer_intake.toml; if it is absent every setting is an assumed default. Every setting, chosen or
assumed, is listed in the page's Model limits dialog under a heading that marks it as a page setting, not part of the
validated model. Answers change only what the page shows first (decision metric, baseline, which levers move,
layout for the audience); they never change the model, its parameters, ranges or the refusal gates.
Standard library only.
"""
import json
import os
import re
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import explorer_release  # noqa: E402
import sd_paths  # noqa: E402

ROOT = os.path.dirname(HERE)
ASSUMED, CHOSEN = "assumed default", "chosen at intake"
LEVERS = {"all": ("All levers", "Every parameter with a validated range is a slider."),
          "policy": ("Policy levers only", "Only the parameters the policy presets change are sliders; the rest are "
                     "shown, held at their base value."),
          "policy+estimated": ("Policy levers and estimated parameters", "Sliders for the parameters the presets "
                               "change and for every parameter tagged 'estimated' in the assumptions register.")}
AUDIENCE = {"decision-makers": ("Decision makers", "Opens on Results: headline numbers and key charts, other charts "
                                "collapsed; the structure on demand."),
            "modellers": ("Modellers", "Opens on Results with every chart group open; the structure shows all variables."),
            "workshop": ("Workshop", "Opens on the Structure tab with flow values shown, for walking a group through the "
                         "feedback loops.")}


class IntakeError(Exception):
    """An answer names an option that does not exist."""


def _spec(project_dir):
    return tomllib.load(open(os.path.join(project_dir, "validation.toml"), "rb"))


def validated_projects(root=None):
    """Projects in the projects root (engine/sd_paths.py) whose release gate passes."""
    root = sd_paths.projects_root() if root is None else root
    out = []
    for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        d = os.path.join(root, name)
        if os.path.exists(os.path.join(d, "validation.toml")):
            try:
                explorer_release.check_release(d)
                out.append(d)
            except explorer_release.Refused:
                pass
    return out


def _js_num(x):
    """A number as JavaScript's String(x) writes it (60 -> "60", 0.1 -> "0.1")."""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return repr(x) if isinstance(x, float) else str(x)


def _sentence_case(text):
    """Same rule as the page (app.js sentenceCase): keep all-caps acronyms and words with digits."""
    out = []
    for i, w in enumerate(text.split(" ")):
        if re.fullmatch(r"[A-Z0-9]{2,}", w) or re.search(r"\d", w):
            out.append(w)
        else:
            out.append(w[:1].upper() + w[1:].lower() if i == 0 else w.lower())
    return " ".join(out)


def metric_label(m, unit):
    """The metric's display label exactly as the page shows it (app.js metricLabel); display text only."""
    tu, var, stat = unit.lower(), m.get("var"), m.get("stat")
    raw = {"value_at": lambda: f"{var} at {tu} {_js_num(m.get('time'))}",
           "time_of_max": lambda: f"{unit} of peak {var}",
           "time_to_reach": lambda: f"{unit} when {var} first reaches {_js_num(m.get('value'))}",
           "final": lambda: f"{var} at the end",
           "initial": lambda: f"{var} at the start"}.get(stat, lambda: f"{stat} of {var}")()
    return _sentence_case(raw)


def baseline_label(spec, name):
    """A preset's name as the page's "Compare against" list shows it (a preset with no changes is the base values)."""
    pol = next((p for p in spec.get("policies", []) if p["name"] == name), None)
    if pol is None or pol.get("changes"):
        return name
    return "base values" if name == "base" else name + " (= base values)"


def defaults(project_dir):
    spec = _spec(project_dir)
    metrics = spec.get("montecarlo", {}).get("metrics", [])
    objective = spec.get("policy", {}).get("objective") or (metrics[0]["name"] if metrics else None)
    pols = [p["name"] for p in spec.get("policies", [])]
    return {"projects": "named", "decision": {"metric": objective, "baseline": pols[0] if pols else "base values"},
            "levers": "all", "audience": "decision-makers"}


def questions(project_dirs=None):
    dirs = [os.path.abspath(d) for d in (project_dirs or [])]
    q = []
    if len(dirs) == 1:
        others = [d for d in validated_projects() if os.path.abspath(d) != dirs[0]]
        opts = [{"key": "named", "label": "Only " + os.path.basename(dirs[0]) + " (default)", "description": "Build this project's page."},
                {"key": "all", "label": "All validated projects", "description": "Build a page for every project whose validation passed."}]
        opts += [{"key": "project:" + os.path.basename(d), "label": "Only " + os.path.basename(d) + " instead",
                  "description": "Build only this project's page."} for d in others[:2]]
        q.append({"id": "projects", "header": "Projects", "question": "Which project page(s) should be built?",
                  "options": opts, "default": "named"})
    else:
        names = [os.path.basename(d) for d in (dirs or validated_projects())]
        opts = [{"key": "all", "label": "All listed (default)", "description": "Build a page for: " + ", ".join(names) + "."}]
        opts += [{"key": "project:" + n, "label": "Only " + n, "description": "Build only this project's page."} for n in names[:3]]
        q.append({"id": "projects", "header": "Projects", "question": "Which project page(s) should be built?",
                  "options": opts, "default": "all"})
    if len(dirs) == 1:
        spec, dflt = _spec(dirs[0]), defaults(dirs[0])
        unit = spec["model"].get("time_unit", "time")
        metrics = {m["name"]: m for m in spec.get("montecarlo", {}).get("metrics", [])}
        obj, base = dflt["decision"]["metric"], dflt["decision"]["baseline"]
        pols = [p["name"] for p in spec.get("policies", [])]
        L = lambda n: metric_label(metrics[n], unit)  # noqa: E731
        B = lambda b: baseline_label(spec, b)  # noqa: E731
        opts = [{"key": "default", "label": f"{L(obj)} vs {B(base)} (default)",
                 "description": f"The decision metric in validation.toml, compared with the '{B(base)}' preset."}]
        same_t = [n for n, m in metrics.items() if n != obj and m.get("stat") == "value_at"
                  and m.get("time") == metrics[obj].get("time")]
        for n in same_t[:2]:
            opts.append({"key": "metric:" + n, "label": f"{L(n)} vs {B(base)}",
                         "description": "Another metric from validation.toml, read at the same time."})
        alt = next((p for p in pols if p != base), "base values")
        opts.append({"key": "baseline:" + alt, "label": f"{L(obj)} vs {B(alt)}", "description": f"Same metric, compared with '{B(alt)}'."})
        q.append({"id": "decision", "header": "Metric", "question": "Which decision metric and baseline should the page lead with?",
                  "options": opts[:4], "default": "default"})
    else:
        q.append({"id": "decision", "header": "Metric", "question": "Which decision metric and baseline should each page lead with?",
                  "options": [{"key": "default", "label": "Each project's own (default)",
                               "description": "[policy].objective from validation.toml, compared with the first policy preset."},
                              {"key": "baseline:base values", "label": "Objective vs base values",
                               "description": "Same metric, compared with the base parameter values."}],
                  "default": "default"})
    q.append({"id": "levers", "header": "Levers", "question": "Which levers should move on the page?",
              "options": [{"key": k, "label": v[0] + (" (default)" if k == "all" else ""), "description": v[1]}
                          for k, v in LEVERS.items()], "default": "all"})
    q.append({"id": "audience", "header": "Audience", "question": "Who is the page mainly for?",
              "options": [{"key": k, "label": v[0] + (" (default)" if k == "decision-makers" else ""), "description": v[1]}
                          for k, v in AUDIENCE.items()], "default": "decision-makers"})
    return q


def resolve(project_dir, answers=None):
    """Settings for one project: every question's value and whether it was chosen or assumed."""
    answers = answers or {}
    unknown = set(answers) - {"projects", "decision", "levers", "audience"}
    if unknown:
        raise IntakeError(f"unknown questions {sorted(unknown)}")
    spec, d = _spec(project_dir), defaults(project_dir)
    metrics = {m["name"] for m in spec.get("montecarlo", {}).get("metrics", [])}
    pols = [p["name"] for p in spec.get("policies", [])] + ["base values"]
    out = {}
    a = answers.get("projects")
    out["projects"] = {"value": a or d["projects"], "source": CHOSEN if a else ASSUMED}
    a = answers.get("decision")
    dec = dict(d["decision"])
    if a and a != "default":
        kind, _, val = a.partition(":")
        if kind == "metric" and val in metrics:
            dec["metric"] = val
        elif kind == "baseline" and val in pols:
            dec["baseline"] = val
        else:
            raise IntakeError(f"decision answer {a!r} is not an option for {os.path.basename(project_dir)}")
    out["decision"] = dict(dec, source=CHOSEN if a else ASSUMED)
    for qid, table in (("levers", LEVERS), ("audience", AUDIENCE)):
        a = answers.get(qid)
        if a is not None and a not in table:
            raise IntakeError(f"{qid} answer {a!r} is not one of {sorted(table)}")
        out[qid] = {"value": a or d[qid], "source": CHOSEN if a else ASSUMED}
    return out


def _q(s):
    return json.dumps(s, ensure_ascii=False)


def record(project_dir, answers=None, mode="asked"):
    if mode not in ("asked", "unattended"):
        raise IntakeError("mode must be 'asked' or 'unattended'")
    s = resolve(project_dir, {} if mode == "unattended" else answers)
    lines = ["# sd-explorer intake (engine/explorer_intake.py). Page settings only: they never change the model, its",
             "# parameters, ranges or the refusal gates. Every setting is listed in the page's Model limits dialog.",
             f"mode = {_q(mode)}", ""]
    for k in ("projects", "levers", "audience"):
        lines += [f"[{k}]", f"value = {_q(s[k]['value'])}", f"source = {_q(s[k]['source'])}", ""]
    lines += ["[decision]", f"metric = {_q(s['decision']['metric'])}", f"baseline = {_q(s['decision']['baseline'])}",
              f"source = {_q(s['decision']['source'])}", ""]
    path = os.path.join(project_dir, "explorer_intake.toml")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    return path


def load(project_dir):
    """Settings the build applies: explorer_intake.toml, or every setting assumed when the file is absent."""
    path = os.path.join(project_dir, "explorer_intake.toml")
    if not os.path.exists(path):
        s = resolve(project_dir, {})
        s["mode"] = "no intake recorded"
        return s
    t = tomllib.load(open(path, "rb"))
    s = resolve(project_dir, {})        # defaults, then the recorded values (re-checked against the spec)
    for k in ("projects", "levers", "audience"):
        if k in t:
            s[k] = {"value": t[k]["value"], "source": t[k]["source"]}
    if "decision" in t:
        s["decision"] = {"metric": t["decision"]["metric"], "baseline": t["decision"]["baseline"], "source": t["decision"]["source"]}
    for k in ("levers", "audience"):
        if s[k]["value"] not in (LEVERS if k == "levers" else AUDIENCE):
            raise IntakeError(f"explorer_intake.toml: {k} = {s[k]['value']!r} is not an option")
    spec = _spec(project_dir)
    if s["decision"]["metric"] not in {m["name"] for m in spec.get("montecarlo", {}).get("metrics", [])}:
        raise IntakeError(f"explorer_intake.toml: decision metric {s['decision']['metric']!r} is not a [montecarlo] metric")
    if s["decision"]["baseline"] not in [p["name"] for p in spec.get("policies", [])] + ["base values"]:
        raise IntakeError(f"explorer_intake.toml: baseline {s['decision']['baseline']!r} is not a preset")
    s["mode"] = t.get("mode", "asked")
    return s


def settings_text(s, spec):
    """Plain-language lines for the Model limits dialog, one per setting."""
    unit = spec["model"].get("time_unit", "time")
    metrics = {m["name"]: m for m in spec.get("montecarlo", {}).get("metrics", [])}
    proj = s["projects"]["value"]
    proj_text = {"named": "this project, as named when /sd-explorer ran", "all": "every validated project"}.get(
        proj, proj.replace("project:", "") + " only")
    m = s["decision"]["metric"]
    return [
        {"setting": "Projects built", "value": proj_text, "source": s["projects"]["source"]},
        {"setting": "Decision metric and baseline",
         "value": f"{metric_label(metrics[m], unit)}, compared with '{baseline_label(spec, s['decision']['baseline'])}'",
         "source": s["decision"]["source"]},
        {"setting": "Levers that move", "value": LEVERS[s["levers"]["value"]][0] + ": " + LEVERS[s["levers"]["value"]][1],
         "source": s["levers"]["source"]},
        {"setting": "Audience", "value": AUDIENCE[s["audience"]["value"]][0] + ": " + AUDIENCE[s["audience"]["value"]][1],
         "source": s["audience"]["source"]},
    ]


def main(argv):
    argv, _ = sd_paths.extract_flag(argv)
    if len(argv) >= 2 and argv[1] == "questions":
        projects = [sd_paths.resolve_project(a) for a in argv[2:]]
        for d in projects:
            problem = sd_paths.project_problem(d)
            if problem:
                print(f"ERROR: {problem}", file=sys.stderr)
                return 1
        if projects:
            sd_paths.adopt_parent(projects[0])
        print(json.dumps(questions(projects), indent=1, ensure_ascii=False))
        return 0
    if len(argv) >= 3 and argv[1] == "record":
        argv[2] = sd_paths.resolve_project(argv[2])
        problem = sd_paths.project_problem(argv[2])
        if problem:
            print(f"ERROR: {problem}", file=sys.stderr)
            return 1
        sd_paths.adopt_parent(argv[2])
        answers = json.loads(argv[argv.index("--answers") + 1]) if "--answers" in argv else {}
        mode = argv[argv.index("--mode") + 1] if "--mode" in argv else "asked"
        print(record(argv[2], answers, mode))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
