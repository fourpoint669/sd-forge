---
description: Build the self-contained interactive explorer page for a validated project (one skippable intake round, then an end-to-end build)
argument-hint: "[<model or path> ...]"
---

Use the `sd-explorer` skill for the project(s) below, a name in the projects root or a path. First do what its "Where things are" section says: find the engine home and the projects root, and stop with its message if sd-forge is not installed. The page is written into the project's folder.

Project(s):

$ARGUMENTS

If no project is named, the intake's first question offers every validated project (default: all of them). Ask the intake round once; every question can be skipped. Then build without stopping, verify, and report.
