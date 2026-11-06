# Modeling process checklist

Use in order; tick each before moving on. Tags: `[unverified]` unless a source is named.

The sequence follows the published account of the modelling process (Sterman (2000) §3.5); the five formulation fundamentals behind steps 4 and 5 — above all that a decision rule may read only information the real decision makers actually have — are that book's own (§13.1.2, Table 13-1). Pointer: `library/notes/sterman-business-dynamics.md`. Nothing here is checked by a script unless its line says so.

1. **Problem articulation**: key variables, time horizon (>= 3x the longest delay), reference mode (historic and expected behavior over time). [unverified; standard SD practice]
2. **Dynamic hypothesis**: draw the CLD; mark each loop R/B; name the archetype if it fits (library/archetypes.md). Check each link's polarity by asking "all else equal, if A rises does B rise or fall?". [unverified]
3. **Boundary**: list endogenous / exogenous / excluded variables. Every important feedback must be endogenous (test T2). [unverified]
4. **Stock-and-flow structure**: identify stocks first; every flow attaches to a stock; no stock without in/out unless intended. Add delays as material (Delay3) or information (Smooth). [unverified]
5. **Parameters**: source each constant (data, literature, estimate) in the model comments; set initial values so the model starts in equilibrium unless the scenario says otherwise. [unverified]
6. **Units**: declare and check (library/units.md).
7. **Run and test**: execute library/validation_tests.md T1-T7 in order; record pass/fail with numbers.
8. **Replicate the reference mode**: compare to history (T5); do not tune structural parameters to hide structural errors.
9. **Policy tests**: change one policy lever at a time; run sensitivity (T7) across plausible ranges.
10. **Document**: model purpose, boundary, assumptions, unit table, test results, sources (by MANIFEST path).
11. **Tool check**: confirm the model translates in PySD (`engine/translate_all.py`) and flag unsupported functions (library/function_compatibility.md).
