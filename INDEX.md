# INDEX

Route: **topic -> table below -> file**. Read order for an agent: (1) this file, (2) the `library/` file named for the topic, (3) the model path listed (full row detail: `MANIFEST.csv`; status detail: `engine/translation_report.csv`).
Status: `runs` = PySD translated and ran; `translates-only` = translated, run failed; `fails` = translation failed; `n/a` = format PySD cannot read.

## Topic routing

| Topic | Read first | Models (best first; up to 5) |
|---|---|---|
| Bass diffusion / adoption | `library/archetypes.md#4-bass-diffusion-r--b-adoption` | none yet |
| SIR / epidemic / contagion | `library/archetypes.md#5-sir-epidemic-r--b` | `raw/test-models/samples/SIR/SIR.mdl` (A, runs)<br>`raw/test-models/samples/SIR/SIR_legacy.stmx` (A, runs)<br>`raw/test-models/samples/SIR/SIR_reciprocal-dt.xmile` (A, runs) |
| Shifting the burden | `library/archetypes.md#7-shifting-the-burden-b--b--r` | none yet |
| Supply chain / inventory / beer game | `library/archetypes.md#6-stock-management-with-delay-b-with-delay` | `raw/test-models/samples/Workforce/workforce.mdl` (A, runs)<br>`raw/sdmr/models/08 Additional/05 Retailer Beer Game/Retailer.mdl` (B, runs)<br>`raw/sdmr/models/08 Additional/05 Retailer Beer Game/Full Beer Model.mdl` (B, translates-only)<br>`raw/bptk-py/website-tutorial/model_library/beergame/simulation_models/beer_game.stmx` (B, fails) |
| World3 / limits to growth | `library/notes/limits-to-growth-world3.md` | `raw/sdmr/models/08 Additional/03 Sensitivity Examples/WorldModel.mdl` (B, runs) |
| Resource depletion / overshoot | `library/archetypes.md#8-resource-depletion-overshoot-and-collapse` | none yet |
| Pricing / competition | `library/archetypes.md#9-market-growth--capacity-r--b-with-delay` | `raw/bptk-py/website-tutorial/model_library/competitive_pricing/simulation_models/competitive_pricing.stmx` (B, runs) |
| Churn / customer acquisition | `library/archetypes.md#9-market-growth--capacity-r--b-with-delay` (validated project: `projects/saas-churn-vs-winrate`) | `raw/sdmr/models/01 Chapter/Vensim/Customers.mdl` (B, runs)<br>`raw/bptk-py/website-tutorial/model_library/customer_acquisition/simulation_models/customer_acquisition.stmx` (B, runs)<br>`raw/bptk-py/website-tutorial/quickstart/xmile/simulation_models/customer_acquisition_xmile.stmx` (B, runs)<br>`raw/bptk-py/website-tutorial/xmile/exporting_simulation_results/simulation_models/customer_acquisition.stmx` (B, runs) |
| Market growth / capacity | `library/archetypes.md#9-market-growth--capacity-r--b-with-delay` | `raw/bptk-py/tests/test_models/test_logistic.stmx` (B, runs) |
| Energy / climate | `library/archetypes.md` | `raw/sdmr/pysd2r/pysd2r_scripts/models/Energy.mdl` (B, runs) |
| Goal seeking (teacup) | `library/archetypes.md#2-goal-seeking-b` | `raw/test-models/samples/teacup/teacup.mdl` (A, runs)<br>`raw/test-models/samples/teacup/teacup_mdl.mdl` (A, runs)<br>`raw/test-models/tests/case_sensitive_extension/teacup-upper.MDL` (A, runs)<br>`raw/test-models/tests/odd_number_quotes/teacup_3quotes.mdl` (A, runs)<br>`raw/test-models/samples/teacup/teacup_legacy.stmx` (A, runs) |
| Predator-prey / population | `library/archetypes.md` | `raw/test-models/samples/Lotka_Volterra/Lotka_Volterra.mdl` (A, runs)<br>`raw/test-models/samples/Population/Subscripted Population Model.mdl` (A, runs)<br>`raw/test-models/samples/bpowers-hares_and_lynxes_modules/model_legacy.stmx` (A, runs)<br>`raw/sdmr/pysd2r/pysd2r_scripts/models/Population.mdl` (B, runs)<br>`raw/sdmr/tidyverse/sdr_paper1/vensim/01 Population Model.mdl` (B, runs) |

## Validated projects (built with /sd-model)

| Project | Question / title | Validation | Read first | Explorer |
|---|---|---|---|---|
| `projects/bass-b2b-adoption` | Summary: adoption of a new B2B software product (Bass diffusion + sales pipeline + churn) | all tests pass | `projects/bass-b2b-adoption/summary.md` | `projects/bass-b2b-adoption/explorer.html` |
| `projects/car-dealership-profit` | How a single-location franchised US car dealership makes money (new, used, leases, F and I, service and parts) and which levers move profit: allocation, resilience, mix, valuation lenses; 67 loops, 15 scenarios | all tests pass + checks.py | `projects/car-dealership-profit/summary.md` | `projects/car-dealership-profit/explorer.html` |
| `projects/saas-churn-vs-winrate` | Fund churn reduction or a higher win rate first over 5 years, and what limits growth (B2B SaaS; ARR, programme budget, CS and enablement capability, sales capacity) | all tests pass + checks.py | `projects/saas-churn-vs-winrate/summary.md` | `projects/saas-churn-vs-winrate/explorer.html` |

## Library files

| File | Content |
|---|---|
| `library/archetypes.md` | archetype catalog: structure, polarity, behavior, equations |
| `library/units.md` | unit conventions |
| `library/function_compatibility.md` | Vensim function vs PySD support (from translation report) |
| `library/modeling_checklist.md` | modeling process |
| `library/validation_tests.md` | tests T1-T7 with numeric tolerances |
| `library/notes/` | chapter-level notes for books/papers (pointers only) |

## Sources

| Source folder | License | commercial_use | Tier | Models | Run OK |
|---|---|---|---|---|---|
| `raw/test-models/` | MIT | yes | A | 278 | 242/278 |
| `raw/pysd/` | MIT | yes | B | 19 | 17/19 |
| `raw/sdeverywhere/` | MIT | yes | B | 85 | 45/85 |
| `raw/bptk-py/` | MIT | yes | B | 71 | 36/71 |
| `raw/readsdr/` | MIT | yes | C | 5 | 2/5 |
| `raw/sdmr/` | MIT | yes | B | 26 | 25/26 |
| `raw/simlin-stdlib/` | Apache-2.0 | yes | B | 8 | 0/8 |

## Pointer-only items (no content stored)

- `pointer:sterman-business-dynamics-2000` — Copyrighted (McGraw-Hill); commercial_use=no; https://mitsloan.mit.edu/
- `pointer:meadows-thinking-in-systems-2008` — Copyrighted (Chelsea Green); commercial_use=no; https://www.chelseagreen.com/product/thinking-in-systems/
- `pointer:meadows-limits-to-growth-1972` — Copyrighted; commercial_use=no; https://www.clubofrome.org/publication/the-limits-to-growth/
- `pointer:meadows-dynamics-of-growth-1974` — Copyrighted; commercial_use=no; https://www.routledge.com/
- `pointer:forrester-industrial-dynamics-1961` — Copyrighted; commercial_use=no; https://mitpress.mit.edu/
- `pointer:morecroft-strategic-modelling-2015` — Copyrighted (Wiley); commercial_use=no; https://www.wiley.com/
- `pointer:bass-1969-new-product-growth` — Copyrighted (INFORMS); commercial_use=no; https://doi.org/10.1287/mnsc.15.5.215
- `pointer:kermack-mckendrick-1927` — Public-domain-era paper; publisher terms not verified; commercial_use=unclear; https://doi.org/10.1098/rspa.1927.0118
- `pointer:senge-fifth-discipline-1990` — Copyrighted; commercial_use=no; https://www.penguinrandomhouse.com/
- `pointer:mit-ocw-15.871` — CC BY-NC-SA 4.0 (per link on course page); commercial_use=no; https://ocw.mit.edu/courses/15-871-introduction-to-system-dynamics-fall-2013/
- `pointer:mit-ocw-15.872` — CC BY-NC-SA (per DSpace record; 4.0 link not re-verified); commercial_use=no; https://ocw.mit.edu/courses/15-872-system-dynamics-ii-fall-2013/
- `pointer:sd-society-proceedings` — (c) System Dynamics Society / authors; no reuse licence stated; commercial_use=unclear; https://proceedings.systemdynamics.org/
- `pointer:pysd-package` — MIT; commercial_use=yes; https://github.com/SDXorg/pysd
- `pointer:openmodelica-world3` — not verified; commercial_use=unclear; https://build.openmodelica.org/Documentation/SystemDynamics.WorldDynamics.World3.html
- `pointer:evaluated-new-world3` — MIT; commercial_use=yes; https://github.com/dasmirlan/New-World3
- `pointer:evaluated-sustainable-energy-transitions` — MIT; commercial_use=yes; https://github.com/csaladenes/sustainable-energy-transitions

Sources that were not downloaded are `pointer:` rows in `MANIFEST.csv`.
- `pointer:pyworld3` — CeCILL-2.1; commercial_use=share-alike; https://github.com/cvanwynsberghe/pyworld3
- `pointer:worlddynamics-jl` — MIT; commercial_use=yes; https://github.com/worlddynamics/WorldDynamics.jl
