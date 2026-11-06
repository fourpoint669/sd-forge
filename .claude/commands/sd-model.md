---
description: Build and validate a system dynamics model for a question, in one of three run modes (full, checkpoint, express)
argument-hint: "[--mode full|checkpoint|express] <question>"
---

Use the `sd-model` skill to run its gated pipeline (10 gates) on this question. First do what its "Where things are" section says: find the engine home and the projects root, and stop with its message if sd-forge is not installed. The model is built in the projects root (the current folder unless `SD_PROJECTS_DIR` is set), not in the engine home.

The question:

$ARGUMENTS

If the question above is empty, ask for one. If it starts with `--mode <mode>`, that is the run mode and the rest is the question; no `--mode` means `checkpoint`; any other mode name, ask. `full` stops for approval after every gate; `checkpoint` pauses once after gate 5 and once at the end; `express` does not pause. In every mode gate 1 still refuses a question that names no decision, a gate 7 failure stops the run, the explorer refusal gates are untouched and no tolerance is loosened. In `checkpoint` and `express`, follow the skill's rules for recording the mode and labelling what no person reviewed. Gate 10 (the explorer page) starts only after gate 9 is approved; its build then runs end to end without stopping.
