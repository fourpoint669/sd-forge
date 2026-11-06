# Gate 8: Policy analysis

Every scenario is run on the **same 1,000 Latin hypercube samples** as the validation (same seed), so each gain below is a
**per-sample difference against the baseline store** (common random numbers). The scenario results reproduce the
validator's `policy_results.csv` to a relative 2.7e-06. Numbers come from
`gate8_analysis.py` (`gate8_results.json`, `scenario_gains.csv`, `resilience.csv`, `loop_dominance_shock.json`).
Units: USD, cumulative net profit before tax; "month 60" is five years from today.

**How to read the absolute bands.** The baseline store's cumulative profit at month 60 spans -$4.22M (P5) to $19.24M (P95), median $6.24M.
Most of that spread is **not dynamics**: the base store starts settled, and monthly profit at month 0 alone already spans
-$66k to $395k (P5 to P95), because the store's own margins, fixed overhead and mix are uncertain (estimated parameters, assumptions register).
The per-sample gains are tighter and are what to compare.

## Lens A: capital allocation (equal added cost of about $10,000 a month, or $600,000 over 60 months)
| Scenario | Gain in cumulative profit, month 60: median (P5 to P95) | Share of samples with a gain | Month 120: median (share positive) | Discounted cash flow gain, month 120, median | Best of all 15 |
|---|---|---|---|---|---|
| A marketing +$10k a month | $131k (-$206k to $605k) | 70% | $576k (82%) | $245k | 0% |
| A used inventory +33 days supply (about $10k a month of carrying cost) | -$504k (-$824k to -$101k) | 4% | -$1.25M (2%) | -$832k | 0% |
| A technicians +1.7 (about $10k a month of payroll) | -$280k (-$556k to $1.48M) | 39% | -$404k (40%) | -$265k | 0% |
| A F and I programme +$10k a month | -$353k (-$528k to -$97k) | 2% | -$705k (2%) | -$434k | 0% |

- **Only marketing beats the baseline more often than not** (70% of samples at month 60, 82% at month 120; median $131k, +0.22 per added dollar). The $10,000 buys about **3.4 extra prospects a month** at the base spend, so this is a thin gain; its driver is the marketing ceiling (maximum marketing starts, Spearman +0.59).
- **Deeper used inventory loses** (median -$504k, a gain in 4% of samples): carrying cost exceeds the extra sales. It is worst when floorplan rates are high (-0.43).
- **An F and I programme loses** (median -$353k, 2% positive): at the base 85% penetration the funded uplift (at most 5 points) is worth less than $10,000 a month in almost every sample. Its driver is the uplift range (+0.80), which is an unsourced estimate.
- **More technicians alone lose in most samples** (median -$280k, positive in 39%) but have the widest upside (P95 $1.48M): they pay only where the service base is larger than assumed (visits per customer +0.66). At the base utilisation of about 0.92, capacity is not the constraint.
- Capital tied up in inventory is not charged in profit (only floorplan interest); the discounted-cash-flow column includes it. The ranking is the same.

## Lens B: resilience (one 12-month window, months 24-36, unless stated)
| Scenario | Gain in cumulative profit, month 60: median (P5 to P95) | Share of samples with a gain | Month 120: median (share positive) | Discounted cash flow gain, month 120, median | Best of all 15 |
|---|---|---|---|---|---|
| B new-vehicle gross -30% for 12 months | -$487k (-$683k to -$325k) | 0% | -$487k (0%) | -$372k | 0% |
| B floorplan rate +3 points for 12 months | -$279k (-$344k to -$215k) | 0% | -$279k (0%) | -$212k | 0% |
| B demand -20% for 12 months | -$49k (-$172k to -$5k) | 1% | -$25k (6%) | -$41k | 0% |
| B all three shocks together, 12 months | -$786k (-$1.03M to -$592k) | 0% | -$768k (0%) | -$611k | 0% |
| B new-vehicle gross -30% for 24 months | -$974k (-$1.37M to -$650k) | 0% | -$974k (0%) | -$706k | 0% |

| Scenario | Lowest monthly net profit in the window: median (P5 to P95) | Change vs baseline, median | Lowest absorption rate in the window, median | Share of months 0-60 with a loss, median |
|---|---|---|---|---|
| baseline store (no lever change) | $97k (-$80k to $322k) | $0k | 0.65 | 0% |
| B new-vehicle gross -30% for 12 months | $58k (-$113k to $272k) | -$40k | 0.65 | 0% |
| B floorplan rate +3 points for 12 months | $76k (-$98k to $297k) | -$23k | 0.65 | 0% |
| B demand -20% for 12 months | $28k (-$134k to $231k) | -$71k | 0.64 | 0% |
| B all three shocks together, 12 months | -$26k (-$188k to $171k) | -$126k | 0.64 | 3% |
| B new-vehicle gross -30% for 24 months | $55k (-$121k to $269k) | -$46k | 0.64 | 0% |

- **A 30% cut in new-vehicle gross costs $487k over 12 months, $974k over 24.** It is the largest single shock and is driven almost entirely by the size of new-car gross per unit (-0.82).
- **The three shocks together cost $786k (P5 to P95 $1.03M to $592k)** and push the lowest monthly net profit in the window to a median of -$26k, a monthly loss in about 3% of months 0-60 (median sample).
- **Fixed ops does not rescue profit in the window.** The lowest absorption rate stays near 0.64 (baseline 0.65) because the shocks hit front-end gross, not service. At about 0.65 the service department covers roughly two thirds of fixed overhead, so a squeeze that cuts front-end gross passes straight to profit.
- **The demand shock is understated.** A 20% drop in shoppers costs only $49k because the model has unserved shoppers wait in the prospect pool and buy later: the shock is a postponement, not lost sales. Treat it as a lower bound (Model limits).
- The baseline itself is fragile: its lowest monthly profit over months 0-60 has a P5 of -$131k, i.e. in more than 5% of samples the store already has a loss-making month with no shock.

## Lens C: business mix
| Scenario | Gain in cumulative profit, month 60: median (P5 to P95) | Share of samples with a gain | Month 120: median (share positive) | Discounted cash flow gain, month 120, median | Best of all 15 |
|---|---|---|---|---|---|
| C used-heavy mix (new share 0.45, used days supply +15) | -$338k (-$1.04M to $469k) | 20% | -$916k (13%) | -$506k | 1% |
| C lease-heavy mix (lease share 0.40) | $93k (-$223k to $364k) | 74% | $500k (82%) | $223k | 0% |
| C fixed-ops: technicians +3 only (capacity, no extra demand) | -$532k (-$984k to $2.51M) | 36% | -$815k (37%) | -$529k | 0% |
| C fixed-ops: service capture x1.25 only (costs nothing in the model: an upper bound) | $2.02M ($166k to $3.63M) | 100% | $5.69M (100%) | $3.02M | 43% |
| C fixed-ops-heavy mix (both of the above) | $2.48M ($1.64M to $3.43M) | 100% | $6.70M (100%) | $3.70M | 56% |

- **Lease-heavy (lease share 0.25 to 0.40):** a small gain (median $93k, 74% positive at month 60, $500k at month 120). Its sign is set by **lease remarketing loss per vehicle** (Spearman -0.78), a parameter with no source (written as a loss per off-lease car: base $200, range -$1,000 to +$1,500). If used prices fall below residuals by more than a few hundred dollars a car, a lease-heavy mix loses.
- **Used-heavy loses** (median -$338k, 20% positive) at the base used gross: it swaps higher new gross per unit for lower used gross and adds carrying cost (new gross per vehicle -0.72). It gains only if new gross stays squeezed.
- **Fixed-ops-heavy: the gain is entirely the service customers, and they are free in this model.** Technicians alone lose (median -$532k); winning 25% more service customers per sale gains $2.02M (P5 to P95 $166k to $3.63M) in **100%** of samples, because `service capture share` has **no cost** here. Both together gain $2.48M. **Read it as a hurdle, not a finding: extra service demand is worth about $2.02M over five years (median; $166k at P5), so a programme that wins 25% more service customers per sale pays if it costs less than that.** Capacity matters only once demand exists: technicians add about $468k on top of the extra demand, but lose $532k without it.
- **Ranking stability (T7b, reported, not gating):** the full ranking of the 15 scenarios repeats in 0.5% of samples; the single best scenario is "both fixed-ops changes" in 56% and "capture only" in 43% (together 99%). So: **which option is best is settled only because the service capture lever is free; the order of the rest is not.** Among the paid options the pairwise orders are close: technicians beat marketing in 37% of samples, lease-heavy beats marketing in 44%.

## Lens D: buying or valuing
Same runs, read as cash. Discounted net cash flow over months 0-120 at the base 10% discount rate (range 7-15%, a stated parameter): median $7.34M, P5 -$6.16M, P95 $24.01M. Undiscounted cumulative profit at month 120: median $11.75M, P5 -$11.00M, P95 $38.21M; at month 180: median $17.01M, P5 -$19.25M, P95 $59.19M.
**This is not a store valuation:** no terminal value, no tax, no real-estate, and the spread is dominated by uncertainty in the store's own economics (below). A price should rest on the seller's actual books; the model supplies how much each assumption moves the answer.

## What moves profit (leverage), from the Spearman table (rank correlation, 1,000 samples)
- **Cumulative profit at month 60:** fixed overhead (-0.47), visits per customer (+0.35), gross per repair order (+0.29), market entry rate (+0.28), parts gross per repair order (+0.27), new gross per vehicle (+0.24).
- **At month 180:** fixed overhead (-0.43), base defection rate (-0.35), market entry rate (+0.33), visits per customer (+0.28), parts gross per repair order (+0.26), gross per repair order (+0.24).
- Reading: the biggest levers on profit are **service economics** (visits per customer, gross per repair order, parts gross, service customer defection) and the **size of the prospect inflow**; **timing and inventory parameters barely matter** (all |rho| under 0.15 for order lead time, adjustment times, availability constants, allocation memory). Since the base starts settled, those matter only after a shock.

## Which loops matter after a shock (the base run is at rest, so its dominance timeline is empty; computed on the three-shocks scenario, `loop_dominance_shock.json`)
- Dominant loops by months: B16 (new-vehicle ordering, 96 of the months), B22 (used sourcing, 35 of the months), B13 (used sourcing, 16 of the months), B2 (first-order adjustment, 2 of the months), B1 (first-order adjustment, 2 of the months), B5 (first-order adjustment, 2 of the months). All are **balancing stock-management loops**: after the shock the store works through it by adjusting new orders and used purchasing, not through the reinforcing replacement and lease echoes.
- Largest mean loop scores: B16 new-vehicle ordering 0.120; B22 used sourcing 0.085; B27 lease echo 0.057; R24 lease echo 0.057; R14 lease echo 0.052; B35 lease echo 0.052. The lease-echo loops (36-month delay) are present but score about 0.05 each, so the lease echo is a **slow, small** contributor in a 15-year run at these parameters.

## What would falsify this model (observations to check against your store)
1. **Marketing:** +$10,000 a month of advertising should add about 3.4 prospects a month at today's spend (diminishing returns). If your lead data shows several times more, or none, the marketing response is wrong.
2. **Squeeze:** a 30% cut in new-vehicle gross per unit for 12 months should lower monthly net profit by about $40k at the trough (median) and leave absorption near 0.65. A much smaller or larger drop means gross-to-profit is mis-specified.
3. **Lease echo:** off-lease returns should follow lease starts with a lag near the lease term (36 months); in the base they are about a quarter of used acquisitions (16.5 of 67 vehicles a month). A store with a clear lease boom three years ago and no matching rise in off-lease units would contradict it.
4. **Service customers:** if winning 25% more service customers per sale costs more than the median $2.02M over five years, the fixed-ops-heavy mix does not pay.
5. **Absorption:** the settled base has an absorption rate of 0.69. If a real store with similar sales has a very different rate, the service or overhead parameters (all estimated) are off, and the profit bands shift with them.
