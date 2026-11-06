# Gate 5: Assumptions register

Confidence tags: **verified** = true by definition or checked in this repo; **reported** = from a cited source, not
checked against the primary document (the figures below were read through web-search summaries of Presidio-NCM data
published by Digital Dealer; the primary NADA / NCM reports were not opened); **estimated** = judgement, derived, or
an order of magnitude with no source found. Most parameters here are **estimated**: dealership benchmarks are
published in aggregate, and no source was found for most response and timing parameters. Every sampled parameter
has a range and a distribution (triangular); store policies and scenario levers are fixed (low = base = high) and change
only through `[[policies]]`. Values match `validation.toml` and `model_spec.py` and become the `.mdl` defaults at gate 6.

**Baseline.** One single-location franchised US store of about 1,000 new and 780 used units a year, with a service
department of about 26 technicians. It is a generic baseline built from benchmark ranges, not one dealership's books.
**Replace the estimated scale parameters with your own store's figures** before relying on any dollar value.


## Parameters: Demand and prospects

| Parameter | Base | Range (distribution) | Unit | Source | Confidence |
|---|---|---|---|---|---|
| shopping rate | 6 | 3 to 10 (triangular); domain [0, 24] | 1/Year | Share of the prospect pool actively shopping per year; 6/yr = a prospect shops about every 2 months. No source; scales with the pool size, which settles to match sales. | estimated |
| new share of shoppers | 0.55 | fixed in the Monte Carlo; lever range 0.35 to 0.75 for exploration; domain [0.05, 0.95] | Dmnl | Store mix, a lens C lever. About 55% new by units is the order of the NADA 2024 sales-dollar split (new 54.7%, used 32.0%, service and parts 13.2%; sales dollars, not units). Fixed; changes only through policies. | estimated |
| market entry rate | 70 | 45 to 95 (triangular); domain [0, 1,000] | Household/Month | New households entering the store's addressable market per month. Set (by running settle.py) so the settled base sales are about 83 new and 65 used units a month, a store of about 1,000 new and 780 used units a year. Replace with your own market data. | estimated |
| maximum marketing starts | 30 | 15 to 50 (triangular); domain [0, 500] | Household/Month | Ceiling on prospects a month that paid marketing can add. No source. | estimated |
| marketing spend scale | 20,000 | 10,000 to 50,000 (triangular); domain [100, 10,000,000] | USD/Month | Spend at which 63% of the marketing ceiling is reached (diminishing returns). No source. | estimated |
| marketing spend | 25,000 | fixed in the Monte Carlo; lever range 0 to 60,000 for exploration; domain [0, 10,000,000] | USD/Month | Store's current monthly advertising and lead cost. A lens A lever; changes only through policies. | estimated |

## Parameters: New vehicles

| Parameter | Base | Range (distribution) | Unit | Source | Confidence |
|---|---|---|---|---|---|
| availability constant new | 8 | 4 to 16 (triangular); domain [0.5, 200] | Vehicle | Stock at which half of new demand can be served from the lot (sales = demand x stock/(stock + constant)). No source. | estimated |
| target new days supply | 60 | fixed (not sampled); domain [5, 200] | Day | Store's stocking policy. Dealer new-car days supply in recent years has been roughly 50-80 days (industry commentary, not checked). Fixed. | estimated |
| new inventory adjustment time | 1.5 | 1 to 3 (triangular); domain [0.1, 24] | Month | How fast ordering closes the gap to target. No source. | estimated |
| order lead time | 1 | 0.5 to 2 (triangular); domain [0.1, 12] | Month | Factory order to delivery. No source. | estimated |
| manufacturer allocation | 160 | 120 to 220 (triangular); domain [0, 2,000] | Vehicle/Month | Hard cap on monthly orders; set above the store's need so it does not bind in the base run. Not a forecast of allocation. | estimated |
| allocation response strength | 0 | 0 to 0.8 (triangular); domain [0, 1] | Dmnl | Optional parameter C (gate 2): extra orders per unit of trailing sales above its reference. 0 = off. Upper end gives +80% orders when trailing sales double. | estimated |
| allocation memory | 6 | 3 to 12 (triangular); domain [0.5, 36] | Month | Averaging time of trailing new sales. Inactive while C = 0. No source. | estimated |

## Parameters: Used vehicles

| Parameter | Base | Range (distribution) | Unit | Source | Confidence |
|---|---|---|---|---|---|
| availability constant used | 8 | 4 to 16 (triangular); domain [0.5, 200] | Vehicle | As for new. No source. | estimated |
| discount demand sensitivity | 1.5 | 0.5 to 3 (triangular); domain [0, 3] | Dmnl | Used demand rises by this multiple of the price discount fraction (1.5 means a 10% discount lifts demand 15%). Domain upper bound 3 with discount sensitivity <= 0.3 keeps demand positive. | estimated |
| discount sensitivity | 0.15 | 0.05 to 0.3 (triangular); domain [0, 0.3] | Dmnl | Price discount fraction per unit of relative excess days supply (0.15: days supply at twice target = 15% discount). | estimated |
| maximum price discount | 0.25 | 0.15 to 0.35 (triangular); domain [0.05, 0.5] | Dmnl | Ceiling on the used price discount (aged units are wholesaled rather than discounted further). With discount demand sensitivity <= 3 it keeps used demand within 1.75x. No source. | estimated |
| target used days supply | 45 | fixed in the Monte Carlo; lever range 30 to 80 for exploration; domain [5, 150] | Day | Store's used stocking policy; 45 days is a common dealer target (industry commentary, not checked). A lens A and C lever; fixed. | estimated |
| used inventory adjustment time | 1.5 | 1 to 3 (triangular); domain [0.1, 24] | Month | How fast purchasing closes the gap to target. No source. | estimated |
| used sales memory | 2 | 1 to 4 (triangular); domain [0.5, 24] | Month | Averaging time of the used-sales rate that days supply is measured against; breaks what would otherwise be an algebraic loop (days supply -> discount -> demand -> sales -> days supply). No source. | estimated |
| reconditioning time | 0.5 | 0.25 to 1 (triangular); domain [0.1, 6] | Month | Acquisition to frontline-ready: about 8-30 days. No source; shortest time constant, sets dt. | estimated |
| wholesale exit rate | 0.5 | 0.25 to 1 (triangular); domain [0, 5] | 1/Year | Share of frontline stock wholesaled per year at target days supply (aged units). No source. | estimated |
| trade in share | 0.25 | 0.15 to 0.4 (triangular); domain [0, 1] | Dmnl | Share of replacing owners whose vehicle the store acquires (trade-in or buy-center); implies trade-ins are about half of used sourcing, a commonly quoted order of magnitude (not checked). | estimated |
| off lease return share | 0.8 | 0.6 to 0.95 (triangular); domain [0, 1] | Dmnl | Share of lease ends where the car comes back to the store (rest are buyouts). No source. | estimated |
| lease remarketing loss per vehicle | 200 | -1,000 to 1,500 (triangular); domain [-5,000, 5,000] | USD/Vehicle | Shortfall of resale value against the lease residual per off-lease vehicle (positive = loss, negative = gain); sign depends on the used-price cycle. Written as a loss so the base is a positive literal (the explorer converter needs that). No source. | estimated |
| used retail price | 28,000 | 24,000 to 32,000 (triangular); domain [5,000, 100,000] | USD/Vehicle | Average used retail price; order of magnitude only. | estimated |
| used vehicle unit cost | 26,500 | 22,000 to 30,000 (triangular); domain [5,000, 100,000] | USD/Vehicle | Used price less gross per unit and recon; order of magnitude only. | estimated |

## Parameters: Customer base and leases

| Parameter | Base | Range (distribution) | Unit | Source | Confidence |
|---|---|---|---|---|---|
| lease share | 0.25 | fixed in the Monte Carlo; lever range 0.1 to 0.5 for exploration; domain [0, 0.9] | Dmnl | Share of new sales that are leases; a lens C lever; fixed. US new-vehicle lease share has run roughly 20-25% in recent years (industry commentary, not checked). | estimated |
| lease term | 36 | 24 to 48 (triangular); domain [12, 60] | Month | Typical 36-month lease; sets the longest delay in the lease echo. | estimated |
| ownership period | 66 | 48 to 96 (triangular); domain [12, 240] | Month | Mean time before an owner replaces. Average ownership of a new vehicle has been quoted at about 6-8 years (not checked). | estimated |
| loyalty floor | 0.1 | 0.05 to 0.2 (triangular); domain [0, 0.3] | Dmnl | Share of replacing owners who return when they have no service relationship. No source. | estimated |
| loyalty ceiling | 0.6 | 0.4 to 0.75 (triangular); domain [0.3, 1] | Dmnl | Share returning with a full service relationship. No source. | estimated |
| loyalty half saturation | 1.5 | 0.5 to 3 (triangular); domain [0.1, 10] | Dmnl | Service customers per owner at which loyalty is halfway from floor to ceiling. No source. | estimated |

## Parameters: Service and parts

| Parameter | Base | Range (distribution) | Unit | Source | Confidence |
|---|---|---|---|---|---|
| service capture share | 2.2 | fixed in the Monte Carlo; lever range 1.6 to 3.2 for exploration; domain [0, 6] | Dmnl | Service customers gained per vehicle sold (buyers plus conquest and outreach); sets service base about 13,000 households and about 1,700 repair orders a month, the order of an average franchised store implied by NADA 2024 service and parts sales of over $156 billion (derived, not checked). Lens C lever; fixed. | estimated |
| base defection rate | 0.25 | 0.15 to 0.4 (triangular); domain [0, 2] | 1/Year | Annual share of service customers lost (tenure about 4 years). No source. | estimated |
| visits per customer | 1.5 | 1 to 2.2 (triangular); domain [0.1, 6] | RO/(Household*Year) | Repair orders per service customer per year. No source. | estimated |
| repairs per technician | 80 | 60 to 100 (triangular); domain [10, 300] | RO/(Technician*Month) | Repair orders a technician completes a month (about 160 flag hours / 2 hours per RO). Productivity benchmarks were not found. | estimated |
| retention loss when overloaded | 0 | 0 to 0.6 (triangular); domain [0, 1] | Dmnl | Optional parameter A (gate 2): extra defection per unit of utilisation above 1. 0 = off. | estimated |
| technician target | 28 | fixed in the Monte Carlo; lever range 20 to 34 for exploration; domain [0, 200] | Technician | Store's hiring target; settled headcount is about 26 after attrition, giving base utilisation near 0.9. A lens A and C lever; fixed. | estimated |
| hire time | 3 | 1.5 to 6 (triangular); domain [0.5, 24] | Month | Recruit and train a technician. No source. | estimated |
| attrition rate | 0.25 | 0.15 to 0.4 (triangular); domain [0, 2] | 1/Year | Technician turnover; the shortage is widely reported but no figure was found. | estimated |
| gross per repair order | 165 | 120 to 220 (triangular); domain [0, 2,000] | USD/RO | Labor gross before technician pay. Calibrated with parts gross and technician cost so fixed-ops gross after pay covers about 70-90% of overhead (NCM H1 2024 average 69.3%, secondary). | estimated |
| parts gross per repair order | 103 | 70 to 140 (triangular); domain [0, 2,000] | USD/RO | Parts gross per RO; same calibration note. | estimated |
| technician cost | 70,000 | 55,000 to 90,000 (triangular); domain [10,000, 300,000] | USD/(Technician*Year) | Loaded annual cost per technician. No source. | estimated |

## Parameters: F and I

| Parameter | Base | Range (distribution) | Unit | Source | Confidence |
|---|---|---|---|---|---|
| F and I base penetration | 0.85 | 0.7 to 0.92 (triangular); domain [0, 0.92] | Dmnl | Share of retail sales with a finance or insurance product. Upper bound 0.92 so penetration plus uplift cannot exceed 1. | estimated |
| F and I maximum penetration uplift | 0.05 | 0 to 0.08 (triangular); domain [0, 0.08] | Dmnl | Extra penetration a funded F and I programme can add. No source. | estimated |
| F and I spend scale | 10,000 | 5,000 to 30,000 (triangular); domain [100, 10,000,000] | USD/Month | Spend at which 63% of the uplift is reached. No source. | estimated |
| F and I programme spend | 0 | fixed in the Monte Carlo; lever range 0 to 20,000 for exploration; domain [0, 10,000,000] | USD/Month | Funded F and I programme on top of base staff cost; 0 in the base store. A lens A lever; fixed. | estimated |
| F and I gross per contract | 2,050 | 1,500 to 2,600 (triangular); domain [0, 20,000] | USD/Household | Chosen so that penetration x gross x (1 - chargebacks) = about $1,570 per retail unit, matching F and I income per retail unit of $1,574 in H1 2024 (Presidio-NCM data via Digital Dealer (secondary; the primary NADA/NCM report was not opened)). | reported |
| chargeback rate | 0.1 | 0.05 to 0.2 (triangular); domain [0, 1] | Dmnl | Share of F and I income reversed by early cancellations. No source. | estimated |

## Parameters: Profit, cost and financing

| Parameter | Base | Range (distribution) | Unit | Source | Confidence |
|---|---|---|---|---|---|
| new gross per vehicle | 2,250 | 1,200 to 3,200 (triangular); domain [-5,000, 20,000] | USD/Vehicle | Average gross profit per new vehicle, full-year 2024 $2,247 (Presidio-NCM data via Digital Dealer (secondary; the primary NADA/NCM report was not opened)). Down 33% on 2023: the base is a squeezed year; range is wide on purpose. | reported |
| used gross per vehicle | 1,400 | 900 to 1,900 (triangular); domain [-5,000, 20,000] | USD/Vehicle | Average gross profit per used vehicle, full-year 2024 $1,399 (Presidio-NCM data via Digital Dealer (secondary; the primary NADA/NCM report was not opened)). | reported |
| fixed overhead | 530,000 | 400,000 to 650,000 (triangular); domain [1,000, 100,000,000] | USD/Month | Fixed expenses excluding technician pay and floorplan interest (rent, salaried staff, owner pay, utilities, insurance). Calibrated at gate 5 (one free parameter, set once) so the settled base earns a pre-tax margin of roughly 2% of sales and an absorption rate near the NCM H1 2024 average of 69.3% (secondary). Both are consistency checks, not data from one store. | estimated |
| commission rate | 0.25 | 0.15 to 0.3 (triangular); domain [0, 1] | Dmnl | Variable selling pay as a share of front-end gross. No source. | estimated |
| wholesale loss per vehicle | 1,200 | 600 to 2,000 (triangular); domain [0, 20,000] | USD/Vehicle | Loss on an aged unit wholesaled. No source. | estimated |
| new vehicle unit cost | 45,000 | 40,000 to 50,000 (triangular); domain [5,000, 150,000] | USD/Vehicle | Invoice cost per new vehicle; order of magnitude. | estimated |
| advance rate | 0.9 | 0.8 to 1 (triangular); domain [0, 1] | Dmnl | Share of inventory cost floorplan finances. No source. | estimated |
| floorplan rate | 0.07 | 0.05 to 0.1 (triangular); domain [0, 0.5] | 1/Year | Floorplan interest rate; order of magnitude, not checked. | estimated |
| discount rate | 0.1 | 0.07 to 0.15 (triangular); domain [0, 1] | 1/Year | Lens D discount rate. A stated parameter, not a finding. | estimated |

## Parameters: Scenario inputs for lens B (zero in the base store)

| Parameter | Base | Range (distribution) | Unit | Source | Confidence |
|---|---|---|---|---|---|
| margin shock size | 0 | fixed in the Monte Carlo; lever range 0 to 0.5 for exploration; domain [0, 1] | Dmnl | Lens B scenario input; 0 in the base. Definition. | verified |
| rate shock size | 0 | fixed in the Monte Carlo; lever range 0 to 0.08 for exploration; domain [0, 0.2] | 1/Year | Lens B scenario input; 0 in the base. Definition. | verified |
| demand shock size | 0 | fixed in the Monte Carlo; lever range 0 to 0.4 for exploration; domain [0, 1] | Dmnl | Lens B scenario input; 0 in the base. Definition. | verified |
| shock start month | 24 | fixed in the Monte Carlo; lever range 0 to 60 for exploration; domain [0, 180] | Month | Shock window start; definition. | verified |
| shock duration | 12 | fixed in the Monte Carlo; lever range 0 to 36 for exploration; domain [0, 180] | Month | Shock window length; policies set 24 for the long squeeze. Definition. | verified |

## Definition constants (not sampled)

| Constant | Value | Unit | Source |
|---|---|---|---|
| months per year | 12 | Month/Year | unit conversion (verified, definition) |
| days per month | 30.4 | Day/Month | 365/12 rounded; unit conversion (verified, definition) |
| vehicles per household purchase | 1 | Vehicle/Household | one vehicle per household purchase; unit conversion (verified, definition) |
| number of lease stages | 3 | Dmnl | three-stage chain gives the lease term a spread of lease lengths (verified, definition) |
| simulation horizon | 180 | Month | gate 1 (180 months) (verified, definition) |
| minimum owner base | 1 | Household | guard against dividing by zero; inactive at base (verified, definition) |
| minimum used sales rate | 1 | Vehicle/Month | guard against dividing by zero; inactive at base (verified, definition) |
| minimum sellout time | 0.25 | Month | physical limit: the lot cannot be emptied faster than this; inactive at base (verified, definition) |

## Initial stocks (fixed; produced by running `settle.py`, not assumed)

`settle.py` is an independent Euler mirror of the equations in `model_spec.py`. It runs the base parameters for 4,000 months and records the stocks. A further 120-month run from the recorded values then moved the largest settled stock by a relative 0 (flat). Cash is the one stock not at rest (it accumulates profit), so its initial value is an arbitrary opening balance.

| Constant | Value | Unit | Source |
|---|---|---|---|
| initial cash | 1,500,000 | USD (arbitrary opening balance) | settle.py: base-parameter steady state (this register); fixed, not sampled |
| initial floorplan debt | 9,511,701 | USD | settle.py: base-parameter steady state (this register); fixed, not sampled |
| initial inventory at cost | 10,568,557 | USD | settle.py: base-parameter steady state (this register); fixed, not sampled |
| initial lessees per stage | 248.0908 | Household (each of 3 stages) | settle.py: base-parameter steady state (this register); fixed, not sampled |
| initial new inventory | 163.2176 | Vehicle | settle.py: base-parameter steady state (this register); fixed, not sampled |
| initial new vehicles on order | 82.6969 | Vehicle | settle.py: base-parameter steady state (this register); fixed, not sampled |
| initial owners | 8,318 | Household | settle.py: base-parameter steady state (this register); fixed, not sampled |
| initial prospects | 315.4555 | Household | settle.py: base-parameter steady state (this register); fixed, not sampled |
| initial reconditioning pipeline | 33.7049 | Vehicle | settle.py: base-parameter steady state (this register); fixed, not sampled |
| initial service customers | 15,492 | Household | settle.py: base-parameter steady state (this register); fixed, not sampled |
| initial technicians | 26.3529 | Technician | settle.py: base-parameter steady state (this register); fixed, not sampled |
| initial used frontline inventory | 87.9466 | Vehicle | settle.py: base-parameter steady state (this register); fixed, not sampled |
| initial used supply outside | 1,000,000 | Vehicle (large source; T3 checks it stays >= 0) | settle.py: base-parameter steady state (this register); fixed, not sampled |
| reference new sales | 82.6969 | Household/Month | settle.py: base-parameter steady state (this register); fixed, not sampled |
| reference used sales | 64.0084 | Household/Month | settle.py: base-parameter steady state (this register); fixed, not sampled |

Derived at build time (formulas, not constants): `Households Outside Market` = (market entry rate + maximum marketing starts) x simulation horizon; `Manufacturer Supply Outside` = manufacturer allocation x simulation horizon.

## Consistency checks of the settled base store against published aggregates (outputs, not inputs)
These come from running `settle.py`; they are consistency checks of the base, not validation (validation is gate 7).
Comparators are **reported** (secondary: Presidio-NCM data as relayed by Digital Dealer, first half of 2024 unless noted).

| Quantity | Base store (settled) | Comparator | Note |
|---|---|---|---|
| New / used sales | 82.7 / 64.0 households a month | none | set by the market entry rate; about 992 new and 768 used a year |
| F and I income per retail unit | $1,568 | $1,574 (H1 2024, reported) | F and I gross per contract chosen to match; so this is by construction |
| Fixed-ops gross share of total gross (before technician pay) | 0.499 | 50.1% (H1 2024, reported) | not adjusted after seeing it: gross per RO and parts gross were set before the first run, aiming at an absorption rate of 70-90% |
| Absorption rate (fixed-ops gross after technician pay / fixed overhead) | 0.689 | 69.3% (H1 2024, reported) | fixed overhead was set once to land near this and a ~2% margin; one free parameter |
| Net profit / revenue proxy | 0.0213 | none found | proxy: vehicles at unit cost plus gross, used at retail price, service at an assumed $480 per RO |
| Used days supply vs target | 41.8 days vs 45 | none | wholesale exits keep realised days supply a little below target (price premium 1.1%) |
| Utilisation of service capacity | 0.919 | none | |

## Structural assumptions (carried into "Model limits")
1. Shoppers who find no stock wait in Prospects; only a purchase removes a prospect.
2. `trade in share` is the share of replacing owners whose vehicle the store acquires, whether or not they buy here.
3. Service customers have their own defection rate and do not drop when their owner is replaced.
4. Used demand rises linearly with the price discount; the sensitivity range is estimated.
5. One shock window (start month, duration) is shared by the margin, rate and demand shocks.
6. `new orders` is capped by `manufacturer allocation` (inactive at base); MIN/MAX appear only as guards or caps.
7. Taxes, body shop, reinsurance, EV/direct sales, competitor response and price elasticity on new cars are excluded (gate 2).
8. The 2024 new-vehicle gross is a squeezed year (down 33% from 2023): the base new-car margin is low by recent history, which makes the fixed-ops and F and I shares look large.

## Decision needed for gate 5 approval: T5 reference function
`engine/validate.py` has one analytic reference, `bass`. This model needs a goal-seeking reference, so I propose one
engine change, **only after your approval**: add `"goal_seeking": lambda t, G, y0, tau: G + (y0 - G) * exp(-t / tau)` to
`ANALYTIC`, one test in `engine/tests/test_validate.py`, and one line in `library/validation_tests.md` T5. No tolerance changes;
the peak check stays optional. The limit case in `validation.toml` is designed so the closed form is exact (derivation in the spec comment).
