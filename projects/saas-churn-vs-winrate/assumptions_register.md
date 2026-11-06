# Gate 5: Assumptions register

Confidence tags: **verified** = checked in this repo or true by definition; **reported** = from a cited source, not
checked against the primary document (all sources below were read through web search summaries or secondary pages);
**estimated** = judgement or derived. Every sampled parameter has a range and a distribution. Monte Carlo (T7)
samples 25 parameters; the 3 scenario levers are fixed and change only through `[[policies]]`. Values match
`validation.toml` and become the `.mdl` defaults at gate 6.

## Parameters: customer engine (same base and range as `projects/bass-b2b-adoption`, sources in its register)

| Parameter | Base | Range (distribution) | Unit | Source | Confidence |
|---|---|---|---|---|---|
| marketing reach rate | 0.14 | 0.05-0.25 (triangular) | 1/Year | Bass p ~ 0.03/yr (Sultan, Farley and Lehmann 1990 meta-analysis, via secondary summaries) / base win rate 0.21 | estimated (derived from reported) |
| word of mouth rate | 1.8 | 1.0-2.9 (triangular) | 1/Year | Bass q ~ 0.38/yr (same) / 0.21 | estimated (derived from reported) |
| sales cycle time | 6 | 3-9 (triangular) | Month | B2B SaaS pipeline benchmarks (Ebsta, KeyBanc as quoted secondhand) | reported (secondary) |
| base win rate | 0.21 | 0.15-0.30 (triangular); domain [0, 0.9] | Dmnl | Gong median ~21% (as quoted secondhand). Domain capped at 0.9 so base + uplift <= 1 | reported (secondary) |
| base annual churn rate | 0.08 | 0.05-0.20 (triangular) | 1/Year | Mid-market logo churn benchmarks, conflicting (ChartMogul, MeltingSpot as quoted) | reported (secondary, conflicting) |
| cool off time | 18 | 12-36 (triangular) | Month | Annual budget and contract cycles; no source | estimated |
| initial total market | 5,000 | 3,000-8,000 (triangular) | Firm | Illustrative. **Replace with your own market sizing.** | estimated |
| initial customers | 10 | 5-25 (triangular) | Firm | Design partners at launch | estimated |

## Parameters: revenue and capacity

| Parameter | Base | Range (distribution) | Unit | Source | Confidence |
|---|---|---|---|---|---|
| new customer ACV | 30,000 | 15,000-60,000 (triangular) | USD/(Firm*Year) | Median B2B SaaS ACV ~$26k (sales-mind KPI benchmarks, secondary, data not shown); mid-market bands are defined as $10k-50k or $25k-100k depending on source. ARR scales with ACV; the ranking per dollar does not scale with it (programme costs do not depend on ACV). | reported (secondary) |
| base net expansion rate | 0.09 | 0.02-0.20 (triangular) | 1/Year | Derived (see "GRR consistency check" below): with 8%/yr logo churn, SaaS Capital's 2025 median NRR of 101% needs a continuous net expansion rate of 0.090/yr. KeyBanc's 2024 median of 102% needs 0.0998; mid-market medians run up to ~108% (Optifai, secondary). Expansion is net of contraction and kept separate from logo churn. Corrected from 0.10 at gate 5 approval (see the check). | estimated (derived from reported) |
| expansion ceiling multiple | 2.0 | 1.3-4.0 (triangular); domain [1, 20] | Dmnl | Average ARR per customer can rise at most to this multiple of new-customer ACV; expansion slows as it approaches (expansion ARR x (1 - ARR per customer / (ACV x multiple))). No benchmark found for lifetime expansion multiples. At 9%/yr net expansion an account doubles in ~8 years, so 2x is reached only by long-tenured accounts; the range spans a near-flat product (1.3x) to strong land-and-expand (4x). Gate 5 change 1. | estimated |
| initial sales capacity (closings per month, won + lost) | 45 | 20-120 (triangular) | Firm/Month | ~15 account executives x ~3 closings a month each. No benchmark found for a launch-stage team; constant for 10 years unless parameter B > 0 (gate 2 item 1). | estimated |

## Parameters: budget and scenario levers

| Parameter | Base | Range (distribution) | Unit | Source | Confidence |
|---|---|---|---|---|---|
| total programme budget | 3,000,000 | 1,500,000-6,000,000 (triangular) | USD | Illustrative: about $50k a month over 60 months, against ARR that starts near $0.3M and reaches ~$10-25M. **Replace with your planned budget.** Identical in every scenario; "no programme" sets it to 0. | estimated |
| phase switch month | 24 | fixed | Month | Decision definition (gate 1: years 1-2, then years 3-5) | verified (definition) |
| churn share phase 1 / phase 2 | 0.5 / 0.5 | fixed; policies set 0 or 1 | Dmnl | Base = 50/50 split (gate 3: every loop active in the base run) | verified (definition) |

## Parameters: programme response curves (all estimated, wide ranges; gate 1 change 2)

| Parameter | Base | Range (distribution) | Unit | Source | Confidence |
|---|---|---|---|---|---|
| CS cost per covered firm | 185 | 100-380 (triangular) | USD/(Firm*Month) | Fully loaded CSM cost ~$95k-160k/yr (StealthAgents, loading unverified; median base salary ~$75-80k per Customer Success Collective and Founderpath) over a mid-market book of ~35-80 accounts (job postings; CS-coverage page). Base $110k / 50 accounts / 12. | reported (secondary, derived) |
| CS ramp up time | 4 | 2-9 (triangular) | Month | Hiring plus onboarding of CSMs; no source | estimated |
| coverage scale | 0.5 | 0.25-1.0 (triangular) | Dmnl | Coverage at which 63% of the maximum churn effect is reached (CS effect = 1 - exp(-coverage / scale)). No source | estimated |
| maximum churn reduction | 0.25 | 0.05-0.45 (triangular) | Dmnl | Weak, conflicting evidence: blog claims of "up to 27%" gross churn reduction (Refiner) and 32% from health-score outreach (Voxbooster), no primary study; Gainsight interviews of ~50 mid-sized SaaS firms found no visible link between CSM headcount share and churn. Range kept wide, low end near zero. | estimated |
| win spend scale | 25,000 | 10,000-60,000 (triangular) | USD/Month | Monthly spend at which 63% of full enablement capability is targeted (target capability = 1 - exp(-spend / scale)). CSO Insights reports an effect above ~$2,500 per rep per year (via Highspot); scale per team is a judgement | estimated |
| enablement ramp up time | 6 | 3-12 (triangular) | Month | Training, content and tool adoption take quarters; no source | estimated |
| maximum win rate uplift | 0.06 | 0.02-0.10 (triangular); domain [0, 0.1] | Dmnl | CSO Insights study: 49.0% vs 42.5% average win rate with vs without enablement (+6.5 points, via Highspot). Survey correlation, not causal; other correlations quoted run to +9 to +18 points but confound leadership quality | reported (secondary, correlational) |

## Parameters: optional sensitivity parameters (gate 2; base 0, so the base case keeps each exclusion)

| ID | Parameter | Base | Range (distribution) | Unit | Source | Confidence |
|---|---|---|---|---|---|---|
| A | expansion lift at full CS effect | 0 | 0-0.10 (triangular) | 1/Year | Upper end: half the gap between mid-market median and top-quartile NRR (~10 points, SaaS Capital / KeyBanc) | estimated |
| B | sales capacity growth rate | 0 | 0-0.5 (triangular) | 1/Year | Time-driven proxy for hiring from revenue; 0.5/yr = 6x capacity over 10 years, linear | estimated |
| C | negative word of mouth multiplier | 0 | 0-2 (triangular) | Dmnl | Each recently churned firm cancels the referrals of C customers; no source | estimated |
| - | market growth rate | 0 | 0-0.10 (triangular) | 1/Year | Linear growth of the target market; no source | estimated |
| - | detractor memory time | 12 | 6-24 (triangular) | Month | How long a churned firm keeps affecting referrals; inactive while C = 0 | estimated |

## Named constants (not sampled)

| Constant | Value | Unit | Reason |
|---|---|---|---|
| months per year | 12 | Month/Year | definition |
| programme months | 60 | Month | decision horizon (gate 1) |
| market growth horizon | 120 | Month | entries stop when the source stock empties at the model's final time (gate 4) |
| minimum customer base | 1 | Firm | keeps CS coverage and ARR per customer finite when Customers = 0 (extreme cases) |
| initial firms in evaluation, initial cooling off firms | 0 | Firm | launch state, as in the worked example |
| CS Capacity, Win Rate Capability, Recently Churned Firms, Cumulative Revenue, Cumulative Programme Spend initial values | 0 | (stock units) | programmes start at month 0; accumulators start empty |

## Structural assumptions

| # | Assumption | Effect if wrong |
|---|---|---|
| S1-S3, S7, S8 | As in `projects/bass-b2b-adoption` (homogeneous firms; returning firms convert like new ones; word of mouth from customers only; continuous firms; consumer-durable Bass coefficients transfer to B2B) | as stated there |
| S9 | Churned customers carry average ARR (churned ARR = ARR x churn fraction) | If smaller accounts churn more, churn reduction saves less ARR per logo; the churn programme is overstated |
| S10 | Programme capability is additional to what the base rates already include; both stocks start at 0 | If current CS or enablement is already saturated, effects are overstated |
| S11 | Diminishing returns have the same exponential form for both programmes; churn saturates in coverage (diluted by growth), win rate in spend | A different curve shape changes the break-even ratio, not the structure |
| S12 | Win-rate uplift applies to every closing, including re-evaluating firms | Overstates win-rate gains if enablement helps new-logo deals only |
| S13 | Sales capacity limits closings (won + lost); excess stays in the pipeline | If excess deals are lost rather than delayed, capacity limits cost more |
| S14 | Fixed dollar schedule, spent evenly per month inside each phase; no reinvestment from ARR (gate 2 item 5) | The ARR-share variant at gate 8 tests this |
| S15 | Market growth is linear and stops at month 120 | Compounding growth would raise late customer counts; the base is 0 |
| S16 | Expansion is limited by a ceiling on **average** ARR per customer, not tracked per cohort or tenure. New logos join at ACV, which lowers the average and reopens headroom for the whole base | Favours the win-rate programme: new logos restart expansion for everyone, while retained (churn-programme) customers fill the ceiling. Listed as limit 6 in `02_boundary.md` |
| S17 | Base net expansion and logo churn are sampled independently, although both come from the same NRR/GRR benchmarks | The sampled NRR spans about 84%-116% (check below), slightly wider than the reported quartiles (97%-114%) |

## Checks beyond validate.py (decided at gate 5, no engine change)
A project script, `projects/saas-churn-vs-winrate/checks.py`, runs at gate 7 **after** `engine/validate.py`. It
writes `checks_results.json` and appends a "Project checks (checks.py)" section with its numbers to
`validation_report.md`, which validate.py rewrites on every run, so the order matters. **Gate 7 passes only if both
scripts exit 0.** If checks.py fails it marks the report WITHHELD and deletes any released `mc_bands.csv`,
`policy_results.csv` and `loop_dominance.json`. `summary.md`, the fan chart and any explorer are withheld unless
both exit 0 (gate 5 change 3). The two checks:
1. **Regression vs `bass-b2b-adoption`:** total budget = 0, A = B = C = 0, base net expansion = 0, market growth = 0,
   initial sales capacity 1e9, all shared parameters at the worked example's base, dt 0.25, months 0-120. Pass: max
   |Customers - example Customers| <= 1e-9 x max(example Customers).
2. **ARR identity:** base net expansion = 0 and A = 0, at the base and fastest-corner parameter sets. Pass: max
   |ARR - Customers x new customer ACV| / max(ARR) < 1e-6.

## Outputs computed at gate 8 (from runs on the same 1,000 samples and seed)
- Funded-scenario bands (the `mc_bands.csv` bands are the no-programme world, since that policy is listed first).
- **Break-even relative cost-effectiveness:** win spend scale multiplied by a sweep of factors, with ARR at month 60 for
  churn-first vs win-rate-first at each factor. Reports the ratio where the ranking flips, with its band across samples.
- ARR lift per dollar = (ARR_m60 scenario - ARR_m60 no programme) / total budget, and net cumulative revenue vs the
  baseline: both per sample.
- Budget as a share of ARR: separate variant model (gate 4), sensitivity only.
- Sensitivity of the ranking to A, B and C across their ranges (gate 2).

## Change to gate 1, stated before any run
Gate 1 expected ARR to be S-shaped. ARR = Customers x average ARR per customer. The per-customer part rises toward
the expansion ceiling at a speed set by uncertain parameters, so the shape of ARR inside 120 months does not follow
from the structure alone. T5 therefore declares modes only for Customers and customer share (s-curve), not for ARR.
Recorded as a dated amendment in `01_problem.md`.

## Sources (read through search results and secondary pages; none checked against the primary report)
- SaaS Capital retention benchmarks: <https://www.saas-capital.com/research/saas-retention-benchmarks-for-private-b2b-companies/>, 2025 report PDF <https://www.saas-capital.com/wp-content/uploads/2025/09/RB32WS1-2025-B2B-SaaS-Retention-Benchmarks.pdf>
- KeyBanc 2024 NRR as quoted: <https://www.stackmatix.com/blog/net-revenue-retention-benchmarks>; mid-market NRR bands: <https://directiveconsulting.com/blog/blog-b2b-saas-retention-benchmarks/>
- Median ACV: <https://sales-mind.ai/blog/post/kpi-benchmarks-saas-sales-teams-2025>
- CSM cost and book size: <https://stealthagents.com/research/cost-of-hiring-a-customer-success-manager-2026>, <https://customersuccesscollective.com/customer-success-salary-report-2024>, <https://founderpath.com/salary-benchmarks/saas/customer-success-manager>, <https://fullview.io/blog/how-many-accounts-customer-success>, <https://www.tomtunguz.com/how-much-arr-can-a-csm-manage/index.md>
- Churn effect of customer success: <https://www.gainsight.com/blog/managing-churn-in-saas-business-with-a-focus-on-customer-success/>, <https://refiner.io/blog/wp-json/wp/v2/posts/2128>, <https://www.voxbooster.com/de/blog/saas-churn-statistics-2026>
- Enablement and win rate (CSO Insights via Highspot): <https://www.highspot.com/blog/cso-insights-finds-mature-sales-enablement-delivers-increasing-business-impact>, <https://highspot.com/blog/25-sales-enablement-stats-to-prove-your-revenue-impact>
- Customer engine sources: `projects/bass-b2b-adoption/sources.md`

## GRR consistency check (gate 5 change 2)
Computed with `.venv/bin/python` (formula: revenue lost to logo churn in a year = 1 - exp(-annual churn rate),
because churned ARR = ARR x churn rate / 12 each month; NRR = exp(net expansion - churn)):

| Quantity | Value |
|---|---|
| Model GRR from base logo churn alone (8%/yr, no programme) | 92.31% (7.69% of revenue lost) |
| Benchmark GRR (SaaS Capital 2025 median) | 91% (9.00% lost) |
| Gap = contraction (downgrades) not modelled as churn | 1.31 points |
| Benchmark gross expansion (NRR 101% - GRR 91%) | 10.0 points |
| Net expansion after that contraction (annual, discrete) | 8.69% |
| Net expansion (continuous) reproducing NRR 101% with 8% churn | 0.0900/yr -> **new base 0.09** |
| Same for KeyBanc NRR 102% | 0.0998/yr (inside the range) |
| Implied NRR at base: 0.09 / 0.10 | 101.0% / 102.0% |
| NRR span when both ranges are sampled independently | 83.5%-116.2% |

**Explanation of the gap.** The model's logo churn explains 7.7 of the 9 points of revenue the benchmark GRR loses.
The remaining 1.3 points are contraction (downgrades), which this model nets into expansion, not churn. The gate 5
draft took the 10-point *gross* expansion as the *net* rate and so double-counted the contraction. The corrected
base, 0.09, reproduces the cited 101% NRR exactly with 8% logo churn. No model has been run, so no result informed
the correction.
