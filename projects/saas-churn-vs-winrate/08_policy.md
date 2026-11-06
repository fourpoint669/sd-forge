# Gate 8: Policy analysis

All numbers come from code run after gate 7 passed (`validate.py` and `checks.py` both exit 0). Sources:
`policy_results.csv` and `validation_results.json` (validate.py), and `gate8_results.json`,
`breakeven_30_30.csv`, `breakeven_24_36.csv` and `scenario_bands.csv` (`gate8_analysis.py`). Configured inputs (parameter bases, ranges and distributions, the optional parameters' defaults A = B = C = 0, sales capacity 45 closings a month with range 20-120, budget $3M with range $1.5M-6M) are set in `validation.toml` and documented with their sources in `assumptions_register.md`; they are inputs, not results. The analysis re-runs every scenario on the **same 1,000 Latin hypercube
samples** (seed 20261029) and reproduces validate.py's released percentiles to within 3.4e-6 relative. Every
comparison below is per sample: the same uncertain world under each policy. No single run is a forecast, and no
policy is stated to be best as a fact.

## Read this first: the defined scenarios mix order with amount
The gate 1 scenarios split the 60 months **24/36**. "Churn first" therefore funds the win-rate programme for **36
months** and churn for 24. "Win rate first" does the reverse. Comparing them mixes *which comes first* with *how
many months each programme gets*. To separate the two, the analysis adds an **order-only** comparison: both orders
on an equal 30/30 split. **This equal split is the primary order result**; the 24/36 scenarios are kept as a
labeled variant.

## Scenario results (ARR at month 60; every scenario spends the same total budget)
No programme: ARR at month 60 P5 $12.0M, median $24.4M, P95 $48.0M (a band from uncertain inputs, not a forecast).

| Scenario | ARR gain vs no programme, P5 / median / P95 | ARR lift per $ of budget, P5 / median / P95 | Cumulative revenue minus spend vs no programme, months 0-60, P5 / median / P95 | P(net cumulative gain > 0) | P(highest ARR at m60) |
|---|---|---|---|---|---|
| win rate only | $2.24M / $5.75M / $13.18M | 0.63 / 1.67 / 4.09 | $1.36M / $7.93M / $22.38M | 0.987 | 0.675 |
| 50/50 split | $2.21M / $5.46M / $11.93M | 0.68 / 1.59 / 3.40 | $1.45M / $7.28M / $19.55M | 0.992 | 0.325 |
| churn first (24 churn, 36 win rate) | $1.68M / $4.01M / $8.53M | 0.48 / 1.16 / 2.65 | -$0.91M / $2.41M / $8.56M | 0.864 | 0.000 |
| win rate first (24 win rate, 36 churn) | $1.56M / $3.61M / $7.26M | 0.49 / 1.04 / 2.26 | $0.64M / $5.51M / $15.16M | 0.979 | 0.000 |
| churn only | $0.56M / $1.54M / $3.54M | 0.17 / 0.44 / 1.09 | -$2.85M / -$0.65M / $2.97M | 0.353 | 0.000 |

"ARR lift per $" = (ARR at month 60 with the programme - without) / total budget: dollars of annual recurring
revenue per programme dollar. Ranking stability (T7b, all six scenarios): the full order repeats in 60.4% of
samples, and the scenario with the highest ARR at month 60 is the same one in 67.5%. **The ranking is not robust.**

## Churn first vs win rate first

### Primary: order only, equal 30/30 split (each programme funded for 30 months, switch at month 30)

| Measure | Churn first ahead | Win rate first ahead | Churn first - win rate first, P5 / median / P95 |
|---|---|---|---|
| ARR at month 60 | **137 of 1,000 (0.137)** | 863 of 1,000 | -$1.84M / -$0.52M / +$0.33M |
| ARR at month 120 | 724 of 1,000 (0.724) | 276 of 1,000 | not computed |
| Cumulative revenue minus spend, months 0-60 | 2 of 1,000 (0.002) | 998 of 1,000 | not computed |

### Variant: the defined gate 1 scenarios, 24/36 split
"Churn first" here funds churn for 24 months and the win-rate programme for **36**. "Win rate first" does the
reverse. This variant therefore mixes order with how many months each programme gets.

| Measure | Churn first ahead | Win rate first ahead | Churn first - win rate first, P5 / median / P95 |
|---|---|---|---|
| ARR at month 60 | **724 of 1,000 (0.724)** | 276 of 1,000 | -$0.61M / +$0.37M / +$2.09M |
| ARR at month 120 | 911 of 1,000 (0.911) | 89 of 1,000 | not computed |
| Customers at month 60 | 963 of 1,000 (0.963) | 37 of 1,000 | not computed |
| Cumulative revenue minus spend, months 0-60 | 0 of 1,000 (0.000) | 1,000 of 1,000 | not computed |

**The two 72.4% figures are different comparisons that happen to share a value.** Both are 724 of 1,000 samples:

| Key in `gate8_results.json` | Split | Measure | Churn first ahead |
|---|---|---|---|
| `p_churn_first_beats_win_first.arr_m60` | 24/36 (variant) | ARR at month 60 | 724 of 1,000 |
| `order_only.p_churn_first_beats_win_first.arr_m120` | 30/30 (primary) | ARR at month 120 | 724 of 1,000 |

In plain terms:
- **With equal months (primary), win rate first is ahead on ARR at month 60 in 863 of 1,000 samples, and on
  cumulative revenue net of spend in 998.** Churn first is ahead by month 120 in 724, because customers kept early
  keep paying and expanding.
- **The 24/36 variant reverses the month-60 result (churn first ahead in 724).** This comes mostly from its 12
  extra months of win-rate funding, not from the order.

## Break-even relative cost-effectiveness

**What k means.** k multiplies the win-rate programme's effect per dollar (its win spend scale is divided by k).
The churn programme keeps its assumed effect per dollar. So k is the win-rate programme's cost-effectiveness
*relative to the churn programme's*, measured against the assumptions in `assumptions_register.md`:
- **k = 1** is exactly as assumed;
- **k = 2**: win-rate dollars work twice as well as assumed, relative to churn dollars;
- **k = 0.5**: half as well.

**k\*** is the k at which churn first and win rate first give equal ARR at month 60 in one sample. **k\* = 1 would
mean the two orders tie when both programmes are exactly as cost-effective as assumed.** Below 1: the tie needs
win-rate dollars to be less effective than assumed. Above 1: more effective. The grid runs from 1/8 to 8 in steps
of sqrt(2). k\* is reported only for samples whose ranking actually flips inside the grid; the rest are counted.

### Primary: 30/30

| k | 1/8 | 0.18 | 1/4 | 0.35 | 1/2 | 0.71 | **1** | 1.41 | 2 | 2.83 | 4 | 5.66 | 8 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P(churn first ahead, ARR m60) | 0.037 | 0.045 | 0.058 | 0.080 | 0.094 | 0.121 | **0.137** | 0.147 | 0.152 | 0.153 | 0.155 | 0.155 | 0.156 |

- **The order does not flip anywhere on the grid in 875 of 1,000 samples:** win rate first leads at every k from 1/8
  to 8 in 841, churn first in 34.
- **125 samples flip inside the grid,** 122 of them from win rate first to churn first as k rises. Their k\*: P5
  0.15, P25 0.30, **median 0.53**, P75 0.82, P95 1.68. 60 of those 125 have k\* between 0.5 and 2.
- **No sample crosses twice.**
- **k\* drivers (Spearman, flipping samples, strongest first):** sales capacity growth -0.33, coverage scale -0.27,
  initial sales capacity +0.27, win spend scale +0.19.
- **Reading:** with equal months, the month-60 ordering is mostly insensitive to how cost-effective the win-rate
  programme is relative to the churn programme. Win rate first stays ahead in most samples even when win-rate
  dollars are 8 times less effective than assumed.

### Variant: 24/36

| k | 1/8 | 0.18 | 1/4 | 0.35 | 1/2 | 0.71 | **1** | 1.41 | 2 | 2.83 | 4 | 5.66 | 8 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P(churn first ahead, ARR m60) | 0.139 | 0.246 | 0.351 | 0.453 | 0.573 | 0.663 | **0.724** | 0.756 | 0.783 | 0.795 | 0.799 | 0.799 | 0.799 |

- **No flip on the grid in 340 samples:** churn first ahead everywhere in 139, win rate first in 201.
- **660 samples flip,** all from win rate first to churn first as k rises (churn first carries 12 more win-rate
  months). Their k\*: P5 0.14, P25 0.21, **median 0.37**, P75 0.64, P95 1.61.
- **No sample crosses twice.**

## What drives the ranking flips (Spearman rank correlation across the 1,000 samples, 25 sampled parameters)

| Difference | Strongest drivers (Spearman) |
|---|---|
| **Churn first - win rate first, 30/30 (primary)** | enablement ramp-up time -0.42; initial sales capacity -0.32; total programme budget -0.23; CS cost per covered firm +0.21; coverage scale +0.21; expansion ceiling multiple -0.20 |
| Churn first - win rate first, 24/36 (variant) | maximum win rate uplift +0.43; enablement ramp-up time -0.32; sales capacity growth rate (B) +0.29; coverage scale +0.29; expansion lift from CS (A) -0.27; maximum churn reduction -0.26 |
| Win rate only - 50/50 (the top-two flip) | maximum win rate uplift +0.45; total programme budget -0.34; maximum churn reduction -0.29; expansion lift from CS (A) -0.28; initial sales capacity +0.27 |
| Win rate only - churn only | maximum win rate uplift +0.53; initial sales capacity +0.38; sales capacity growth rate (B) +0.31; new customer ACV +0.29; base annual churn rate -0.23 |

Churn first ahead at month 60, 30/30 (primary), by tercile of the four strongest drivers (count of 333-334 samples;
ranges in brackets are the configured ranges from `validation.toml`):

| Driver | Low third | Middle third | High third |
|---|---|---|---|
| enablement ramp-up time (3-12 months) | 78 | 48 | 11 |
| initial sales capacity (20-120 closings/month) | 71 | 42 | 24 |
| total programme budget ($1.5M-6M) | 46 | 56 | 35 |
| CS cost per covered firm ($100-380/firm/month) | 25 | 40 | 72 |

Churn first ahead at month 60, 24/36 (variant), by tercile (share of samples; configured ranges from `validation.toml`):

| Driver | Low third | Middle third | High third |
|---|---|---|---|
| maximum win rate uplift (0.02-0.10) | 0.53 | 0.77 | 0.87 |
| enablement ramp-up time (3-12 months) | 0.80 | 0.77 | 0.60 |
| sales capacity growth rate B (0-0.5/yr) | 0.62 | 0.75 | 0.80 |
| coverage scale (0.25-1.0) | 0.59 | 0.73 | 0.85 |

Optional parameters (gate 2; defaults and ranges from `validation.toml`):
- **A (expansion lift from CS)** pulls toward the churn-heavy options: Spearman -0.17 (30/30), -0.27 (24/36),
  -0.28 (win rate only - 50/50).
- **B (sales capacity growth)** does not move the 30/30 order (+0.01) but pulls toward win rate in the other
  comparisons (+0.29, +0.25).
- **C (negative word of mouth)** has almost no effect inside its 0-2 range (|Spearman| about 0.06 at most; the largest is 0.060, for
  win rate only - 50/50).

## What limits growth: loop dominance (base parameter set, one run; structure, not a forecast)

**Model-wide** (`loop_dominance.json`, as released by validate.py; LTM scores normalized across all 22 loops):

| Months | Dominant loop |
|---|---|
| 0-0.5 | B8 enablement adjustment |
| 0.5-1 | B9 detractor fade |
| 1-6.25 | B8 enablement adjustment |
| 6.25-8.25 | B6 cool-off drain |
| 8.25-8.5 | R1 word of mouth |
| 8.5-12 | B3 churn |
| 12-21.5 | B10 ARR churn |
| 21.5-60 | B9 detractor fade |
| 60-60.75 | B1 saturation via word of mouth |
| 60.75-65.75 | B9 detractor fade |
| 65.75-67 | B6 cool-off drain |
| 67-120 | B9 detractor fade |

B9 sits on an information side-stock (recently churned firms) that does not affect customers while C = 0. B8 and
B10 sit on the enablement and ARR stocks. Model-wide normalization lets such side loops top the ranking, so this view
does not answer "what limits customer growth".

**Customer-restricted** (same scores, renormalized over only the loops that pass through Customers; computed in
`gate8_analysis.py`):

| Months | Dominant loop among customer loops | Mean share |
|---|---|---|
| 0.25-8.5 | R1 word of mouth | 0.86 |
| 8.75-120 | B3 churn | 0.96 |

Statements about what limits customer growth below use **only the customer-restricted view**, labeled as such.

## Leverage, explained by loops (structure, not a forecast)
- **Customer-restricted view.** Word of mouth (R1) dominates the customer loops in months 0.25-8.5, and churn (B3)
  dominates in months 8.75-120 (`dominance_customer_loops_base_run`).
- **The switch coincides with sales capacity starting to bind.** At base parameters capacity first binds at month
  8.5, with or without the programme. Once closings are capped (`deal closings = MIN(pipeline / cycle, capacity)`),
  more evaluations no longer add customers, the word-of-mouth loop is cut at the pipeline, and customers move with
  capacity x win rate - churn.
- **How often capacity binds across samples.** Before month 60 it binds in 515 of 1,000 samples with no programme,
  and in 525-564 with a programme. The median share of months 0-60 at the limit is 0.25 with no programme and up to
  0.49 under win rate only.
- **Why win rate leads at month 60 in this model.** A higher win rate raises wins per capped closing directly, and
  the win-rate programme also feeds R1 while capacity is free. Churn reduction acts through B3 and through CS
  coverage, which growth dilutes (B11), so its gain builds slowly and shows by month 120.
- **This finding is conditional on the sales-capacity input.** `initial sales capacity` (base 45 closings a month,
  range 20-120) is an **illustrative estimate with no benchmark behind it**, and it is constant for 10 years unless
  B > 0. "Sales capacity limits growth" holds only as far as that input describes your sales team. Initial capacity
  is the second-strongest driver of the 30/30 order (Spearman -0.32). The more sales capacity, the less often churn
  first is ahead at month 60: 71, 42 and 24 samples across its low, middle and high thirds.

## What holds across samples, and what does not
**Holds (in >= 95% of samples, or by construction):**
- Every mix that includes the win-rate programme raises ARR at month 60 over no programme (P5 gains $1.6M-2.2M).
  Churn only raises it too, but by the least (P5 $0.56M).
- Churn only is the weakest funded option at month 60: below every other mix in 97.9%-100% of samples, and net of
  its cost it loses money over months 0-60 in 64.7% of samples.
- With equal months (30/30), win rate first gives more cumulative revenue net of spend over months 0-60 than churn
  first (998 of 1,000), and more ARR at month 60 in 863 of 1,000. Across a 64-fold range of relative
  cost-effectiveness (k from 1/8 to 8), **841 of 1,000 stay win rate first at every k**. A further 34 stay churn
  first, so 875 never change order; the other 125 flip.
- 50/50 beats both sequenced scenarios at month 60 (99.5% and 100%).

**Does not hold (the answer flips with uncertain inputs):**
- **Win rate only vs 50/50 split** (67.5% vs 32.5%). It turns on how large the win-rate uplift really is, the
  budget, and how much CS cuts churn or lifts expansion.
- **Churn first vs win rate first, beyond month 60 or with unequal months.** By month 120 churn first leads in 724
  of 1,000 (30/30) and 911 of 1,000 (24/36). With the 24/36 split, churn first leads at month 60 in 724 of 1,000.
  The answer depends on horizon and split.
- **The break-even ratio where it exists.** Among the 125 samples (30/30) that flip, the median k\* is 0.53 with a
  90% band of 0.15-1.68. For 24/36 (660 flipping samples) the median is 0.37, band 0.14-1.61.
- **Whether sales capacity is the binding limit.** It binds before month 60 in about half the samples, and that
  share rests on an illustrative capacity input.
- **Monte Carlo spread.** Per-dollar lifts span 4.6-6.5x between P5 and P95, depending on the scenario. The
  programme response parameters behind them are tagged `estimated` (win-rate uplift `reported`, correlational). This
  gate has not decomposed how much of the spread each parameter causes.

**Model limit specific to this gate:** sales capacity (`initial sales capacity`, 45 closings a month, range
20-120, constant unless B > 0; configured in `validation.toml`, see `assumptions_register.md`) is illustrative. The finding that sales capacity limits customer growth from about
month 8.5, and the explanation of why win rate leads at month 60, are conditional on it. It is carried into
**Model limits** in `summary.md`.

**Not done at this gate:** the budget-as-share-of-ARR variant (gate 1 sensitivity) needs its own model and its own
validation. It has not been built, so nothing about it is reported.

## What observation would falsify the model
The "model expectation" column holds two kinds of number:
- **Benchmark inputs** (labeled): the configured ranges in `validation.toml`, derived from secondary benchmarks
  listed in `sources.md` and documented in `assumptions_register.md`. They are not results.
- **Model results** (labeled): computed in `gate8_results.json`.

The "measured over 2-3 quarters" suggestion is a measurement design, not a number from the model.

| Observation | Model expectation | If violated |
|---|---|---|
| Win-rate change after enablement (suggested window: 2-3 quarters) | **Benchmark input:** +2 to +10 points at full capability (`maximum win rate uplift` 0.02-0.10), reached over 3-12 months (`enablement ramp up time`) | A smaller effect moves the comparison toward the churn-heavy options; refit `maximum win rate uplift` and rerun gates 7-8 |
| Logo churn among CS-covered vs uncovered accounts | **Benchmark input:** 5-45% lower at full coverage (`maximum churn reduction` 0.05-0.45) | No difference (as Gainsight's interviews suggest, `sources.md`) means the churn programme's value here is overstated |
| Deal closings vs sales headcount (sales capacity is an illustrative input) | **Model result:** capacity binds before month 60 in 515-564 of 1,000 samples, from month 8.5 at base parameters (`gate8_results.json`) | Closings rising freely with pipeline means capacity is mis-specified, and the explanation for why win rate leads fails |
| Expansion of CS-covered accounts | **Benchmark input:** no extra expansion at base (`expansion lift at full CS effect` = 0, range 0-0.10/yr) | Covered accounts expanding faster means A > 0, which moves the result toward churn |
| Net revenue retention (NRR) of your customer base: next year's recurring revenue from today's customers / today's recurring revenue | **Benchmark input:** at base, NRR about 101% (base churn 8%/yr and net expansion 9%/yr; GRR about 92% before contraction; GRR consistency check in `assumptions_register.md`). The reported benchmark range is 97%-114% (bottom to top quartile, `sources.md`). Sampling churn and expansion independently gives NRR between 83.5% and 116.2%, wider than the benchmark range (assumption S17) | **Inside 83.5%-116.2% but far from 101%:** the bands still cover you, but re-centre churn and expansion on your values and rerun gates 7-8. **Outside 83.5%-116.2%:** the sampled ranges do not cover your business; widen or move them before using any result |
