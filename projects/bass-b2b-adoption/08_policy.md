# Gate 8: Policy analysis

All numbers are from `validation_report.md` / `policy_results.csv` (engine/validate.py, N = 1,000 Latin hypercube samples, seed 20261029, common random numbers: every scenario runs on the same 1,000 parameter sets).

## Scenarios
Each lever is improved by **20% of its own base value**, so the comparison shows leverage per unit of change. Costs are not modelled: a +20% win rate may cost far more (or less) than +20% marketing reach. Read this as "where does a unit of improvement move adoption most", not as ROI.

Objective: paying customers at month 60 (the decision horizon).

| Scenario | P5 | Median | P95 | Gain vs base, P5 | Median | P95 |
|---|---|---|---|---|---|---|
| base | 410 | 719 | 1,243 | 0 | 0 | 0 |
| win rate +20% (0.21 -> 0.25) | 522 | 916 | 1,584 | +112 | +193 | +330 |
| marketing reach +20% | 458 | 793 | 1,361 | +48 | +73 | +114 |
| word of mouth +20% | 442 | 775 | 1,343 | +26 | +51 | +102 |
| churn -20% (8% -> 6.4%/yr) | 434 | 759 | 1,304 | +20 | +37 | +71 |
| sales cycle -20% (6 -> 4.8 months) | 426 | 755 | 1,307 | +17 | +35 | +67 |

Ranking stability (T7b): **win rate is the best lever in 100% of the 1,000 samples.** The full ordering of all six scenarios repeats in only 34.1% of samples, because churn and sales-cycle gains are close and swap places. Conclusion that survives the uncertainty: win rate first, marketing reach second; the order of the last three is not robust.

## Leverage points (why the model ranks them this way)
1. **Win rate** acts three times: it converts every evaluation, it speeds the word-of-mouth loop R1 (more customers produce more referrals), and it shrinks the flow of lost deals into cool-off, which keeps firms in the potential pool. It is also the parameter with the strongest correlation with market share at months 60 and 180 (Spearman +0.66 and +0.55).
2. **Marketing reach** dominates the first year (Spearman +0.70 with customers at month 12) and the time to 10% share (-0.69); its effect fades as word of mouth takes over.
3. **Churn** barely matters inside 5 years (Spearman -0.20 at month 60) but is the strongest driver of long-run share (-0.65 at month 180): it sets the ceiling, not the speed.
4. **Sales cycle** matters mainly in the first year (-0.30 at month 12): it delays every loop that runs through the pipeline but does not change where the curve ends.

Loop dominance (T8, base case) agrees: marketing saturation and pipeline/cool-off filling dominate months 0-16; word of mouth (R1) dominates months 16-79; after that, recycling of lost deals through word of mouth (R3) dominates most of the remaining time, with the saturation loop B1 briefly dominant (months 91-101). Market saturation never dominates for long inside 15 years.

## Long-run ceiling (structural property, not a forecast)
A 1,200-month run at base parameters settles at about 2,323 customers (46% share), with 907 firms potential, 443 in evaluation and 1,328 cooling off; with churn set to 0 the share approaches 100% (98.1% at month 600). Reproduce:

```bash
.venv/bin/python -I -c "import sys; sys.path.insert(0,'engine'); import validate; py='projects/bass-b2b-adoption/model/bass_b2b_adoption.py'; [print(round(d['customer share'].iloc[-1],3)) for d in validate.run_batch(py,[{'final_time':1200,'saveper':12},{'final_time':1200,'saveper':12,'params':{'annual logo churn rate':0.0}}])]"
```

So the market-saturation limit the question asks about is real but far away: about 46% at base, reached only after decades; inside 15 years the median is 31%.

## What would falsify the model
| Observation | Model expectation | If violated |
|---|---|---|
| Customers at month 12 | 57-179 (P5-P95) | Outside the band: p, q or win rate ranges are wrong, or a missing constraint binds (rerun with your data). |
| Months to 10% customer share | 31-73 (P5-P95) | Reached before month 31 or not by month 73: same as above. |
| Share of new evaluations that come from referrals | rises as customer share rises (R1) | Flat or falling referral share while the base grows: R1 is mis-specified (word of mouth may not scale with share). |
| Win rate of re-evaluating firms (lost or churned before) | same as fresh prospects (assumption S2) | Materially lower: R2-R5 overstate late growth; months 80+ are optimistic. |
| Deals won vs sales headcount | no capacity limit (S4) | Deals won flat while pipeline grows: a capacity loop is binding; the model must add it. |
| Logo churn in the first 2 years | 5-20%/yr | Outside: churn range wrong; long-run share band moves. |

A single falsifying observation does not mean the structure is useless; it means recalibrate the range or add the missing loop and re-run gate 7.
