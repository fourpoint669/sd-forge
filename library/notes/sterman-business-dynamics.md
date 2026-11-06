# Sterman, Business Dynamics (2000) — section pointers

`[verified: section and page numbers read from the book's table of contents and from the pages cited below, 2026-11-02]`

Sterman, J. D. (2000). *Business Dynamics: Systems Thinking and Modeling for a Complex World*.
Boston: Irwin/McGraw-Hill. ISBN 0-07-231135-5 (ISBN-13 978-0-07-231135-8).

Own words only; no passage, table or figure from the book is stored here. Licence record:
`MANIFEST.csv` row `pointer:sterman-business-dynamics-2000` (copyrighted, `commercial_use=no`).
This note maps only the sections this repository actually draws on, not the book's contents.

## What this repository takes from it, section by section

| Used by | Section |
|---|---|
| `library/archetypes.md` 1-3: exponential growth, goal seeking, S-shaped growth, overshoot and collapse | §4.1-4.3, pp. 108-133 |
| `library/modeling_checklist.md` steps 1-10: the modelling process | §3.5, pp. 89-103 |
| `library/archetypes.md` loop polarity and naming conventions; gate 3's CLD rules | ch. 5, pp. 137-190 |
| T6 conservation, the snapshot test, auxiliaries, stock-and-flow units | ch. 6, pp. 191-229 |
| `loop_detector.py` dominance timeline: the formal definition of loop dominance | §8.5.1, p. 288 |
| `library/archetypes.md` 4: the Bass diffusion model | §9.3.3, p. 332 |
| `library/archetypes.md` 5: SIR, the tipping point, herd immunity | §9.2, pp. 300-321 |
| Material and information delays, their orders and distributions | ch. 11, pp. 409-466 |
| Little's Law, as the stock/throughput/delay-time identity | §11.2.6, p. 421 |
| Erlang-distributed higher-order delays and Koyck lags | §11.7, pp. 462-466 |
| Aging chains; coflows as the attributes of a stock | §12.1 p. 470, §12.2 p. 497 |
| The rate-equation catalogue (fractional rates, adjustment to a goal, the stock management structure, fuzzy MIN/MAX, floating goals) | §13.2, pp. 522-544 |
| The three formulation pitfalls: first-order control of outflows, avoiding IF-THEN-ELSE, disaggregating net flows | §13.3, pp. 545-549 |
| Table-function conventions: normalisation, reference point, endpoints, no hump-shaped functions | ch. 14, pp. 551-595 |
| Partial model tests of a decision rule's intended rationality | §15.4.1, p. 605 |
| Expectation formation and the TREND function | §16.1.1, p. 634 |
| Amplification, phase lag, the stock management structure with a supply line | §17.1.1 p. 664, §17.3 p. 675 |
| Supply-line neglect as a source of oscillation | §17.4.1 p. 684, §17.4.2 p. 695 |
| Initialising a model in equilibrium; simultaneous initial conditions | §18.1.5, pp. 716-718 |
| `library/validation_tests.md`: the model test families | §21.4, pp. 858-889 (see the attribution note below) |
| `library/units.md` rule 8 and T4: time-step choice and the integration-error test | appendix A, pp. 903-910 |
| White and pink noise, correlation time, the amplitude scaling that makes output sigma match the specification | appendix B, eqs. B-4 to B-6, pp. 918-919 |

## Attribution: cite the chain where the book cites one

Several things this repository uses are credited in the book itself to earlier work. Citing only
Sterman for them would over-credit him and misstate where they came from.

| Item | Primary source, as the book gives it |
|---|---|
| The model test families that `library/validation_tests.md` operationalises (Table 21-4) | "Adapted and extended from Forrester and Senge (1980)" |
| Protective versus reflective uses of models (Table 21-3) | "Adapted and revised from Isaacs and Senge (1992, p. 191)" |
| Little's Law | Little (1961), cited at §11.2.6 |
| Erlang delay distributions and Koyck lags | Koyck (1954) and the Erlang distribution, cited at §11.7 |
| The pink-noise formulation | the DYNAMO lineage; the book gives the equations, not their origin |
| Loops That Matter link and loop scores | Schoenberg, Davidsen and Eberlein (2020), already cited in `engine/loop_detector.py` — not from this book |

What is the book's own contribution, and should be credited to it squarely:

- **The five formulation fundamentals**, including the **Baker Criterion** (a decision rule may read
  only information the real decision makers actually have): §13.1.2, Table 13-1, pp. 516-517. The
  naming and the synthesis are his.
- The organisation of the field into a single teachable method, which is what
  `library/modeling_checklist.md` and the `/sd-model` gate sequence follow.

## Caveat

A citation is not a licence. Crediting the book does not permit reproducing its text, tables or
figures, here or in any output of this repository. Chapter and page numbers above are from the
printing identified by the ISBN; check against your own copy before relying on them.
