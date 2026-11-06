# Gate 4: Stock-flow structure

Time unit: **Month**. Rates given per year in sources are converted with the named constant `months per year` =
12 Month/Year (`library/units.md` rule 4), never a bare 12. Every delay is an explicit stock (no SMOOTH/DELAY).
Functions used are limited to those T1 can check: `IF THEN ELSE`, `MIN`, `MAX`, `EXP`, `Time` (`engine/validate.py`
`infer_units`); no `XIDZ`. Literal numbers are only 0 and 1. Parameter values, ranges and sources come at gate 5.

## Stocks

| # | Stock | Unit | Inflows | Outflows | Initial value | Kind |
|---|---|---|---|---|---|---|
| 1 | Potential Customers | Firm | re entry, market entries | evaluation starts | initial total market - initial customers | material |
| 2 | Firms in Evaluation | Firm | evaluation starts | deals won, deals lost | initial firms in evaluation | material (sales-cycle delay) |
| 3 | Customers | Firm | deals won | churn | initial customers | material |
| 4 | Cooling Off Firms | Firm | deals lost, churn | re entry | initial cooling off firms | material (cool-off delay) |
| 5 | Firms Yet To Enter | Firm | none | market entries | initial firms yet to enter | material source for market growth |
| 6 | Recently Churned Firms | Firm | churn | detractor fade | 0 | information co-flow (detractor memory) |
| 7 | CS Capacity | Firm | CS capacity change (bi-flow) | | 0 | resource (customers the programme can cover; ramp-up delay) |
| 8 | Win Rate Capability | Dmnl | capability change (bi-flow) | | 0 | resource (enablement level; ramp-up delay) |
| 9 | ARR | USD/Year | new ARR, expansion ARR | churned ARR | initial customers x new customer ACV | money rate |
| 10 | Cumulative Revenue | USD | revenue recognition | none | 0 | accumulator |
| 11 | Cumulative Programme Spend | USD | total programme spend | none | 0 | accumulator |

Stocks 7 and 8 start at 0: they are the programme's **additional** capacity on top of what the base churn and win rate
already reflect. Churn feeds both Cooling Off Firms (the firm itself) and Recently Churned Firms (a count of recent
churners); the second is information, not material, so it is outside the conservation group.

## Flows and auxiliaries

| Variable | Equation | Unit |
|---|---|---|
| marketing driven starts | marketing reach rate monthly x Potential Customers | Firm/Month |
| word of mouth starts | word of mouth rate monthly x Potential Customers x MAX(0, customer share - negative word of mouth multiplier x detractor share) | Firm/Month |
| evaluation starts | marketing driven starts + word of mouth starts | Firm/Month |
| customer share | Customers / total market | Dmnl |
| detractor share | Recently Churned Firms / total market | Dmnl |
| total market | initial total market + initial firms yet to enter - Firms Yet To Enter | Firm |
| market entries | market growth rate monthly x initial total market x market growth active | Firm/Month |
| market growth active | IF THEN ELSE(Time < market growth horizon, 1, 0) | Dmnl |
| initial firms yet to enter | market growth rate x initial total market x market growth horizon / months per year | Firm |
| deal closings | MIN(Firms in Evaluation / sales cycle time, sales capacity) | Firm/Month |
| sales capacity | initial sales capacity x (1 + sales capacity growth rate x Time / months per year) | Firm/Month |
| effective win rate | base win rate + maximum win rate uplift x Win Rate Capability | Dmnl |
| deals won; deals lost | deal closings x effective win rate; deal closings x (1 - effective win rate) | Firm/Month |
| churn | Customers x effective churn fraction | Firm/Month |
| effective churn fraction | base churn rate monthly x (1 - churn reduction) | 1/Month |
| re entry | Cooling Off Firms / cool off time | Firm/Month |
| detractor fade | Recently Churned Firms / detractor memory time | Firm/Month |
| monthly programme budget | total programme budget / programme months | USD/Month |
| programme active | IF THEN ELSE(Time < programme months, 1, 0) | Dmnl |
| churn share now | IF THEN ELSE(Time < phase switch month, churn share phase 1, churn share phase 2) | Dmnl |
| churn programme spend | monthly programme budget x programme active x churn share now | USD/Month |
| win rate programme spend | monthly programme budget x programme active x (1 - churn share now) | USD/Month |
| total programme spend | churn programme spend + win rate programme spend | USD/Month |
| funded CS capacity | churn programme spend / CS cost per covered firm | Firm (cost in USD/(Firm*Month)) |
| CS capacity change | (funded CS capacity - CS Capacity) / CS ramp-up time | Firm/Month |
| CS coverage | CS Capacity / MAX(Customers, minimum customer base for coverage) | Dmnl |
| CS effect | 1 - EXP(-CS coverage / coverage scale) | Dmnl (diminishing returns) |
| churn reduction | maximum churn reduction x CS effect | Dmnl |
| target capability | 1 - EXP(-win rate programme spend / win spend scale) | Dmnl (diminishing returns; scale in USD/Month) |
| capability change | (target capability - Win Rate Capability) / enablement ramp-up time | 1/Month |
| expansion lift | expansion lift at full CS effect x CS effect | 1/Year (parameter A, default 0) |
| effective expansion rate | base net expansion rate + expansion lift; monthly = / months per year | 1/Year; 1/Month |
| new ARR | deals won x new customer ACV | USD/(Year*Month) |
| expansion ARR | ARR x effective expansion rate monthly | USD/(Year*Month) |
| churned ARR | ARR x effective churn fraction | USD/(Year*Month) |
| revenue recognition | ARR / months per year | USD/Month |
| cumulative revenue net of programme spend | Cumulative Revenue - Cumulative Programme Spend | USD |
| marketing reach rate monthly, word of mouth rate monthly, base churn rate monthly, market growth rate monthly | annual rate / months per year | 1/Month |

Unit checks by hand (T1 repeats them on the PySD translation): new ARR = Firm/Month x USD/(Firm*Year) =
USD/(Year*Month), the unit of ARR (USD/Year) per Month. Revenue recognition = (USD/Year) / (Month/Year) = USD/Month,
so Cumulative Revenue is in USD: this is the /12 conversion approved at gate 1. Funded CS capacity = (USD/Month) /
(USD/(Firm*Month)) = Firm. Initial firms yet to enter = 1/Year x Firm x Month / (Month/Year) = Firm.

Budget schedule: with `programme months` = 60 and a time step that divides 60 (gate 5), Euler spends exactly
60 x monthly budget, so Cumulative Programme Spend at month 60 equals the total budget in every scenario. Scenarios
differ only in `phase switch month`, `churn share phase 1` and `churn share phase 2` (churn first: 24, 1, 0; win rate
first: 24, 0, 1; 50/50: 24, 0.5, 0.5; churn only: 24, 1, 1; win rate only: 24, 0, 0); "no programme" sets the
total budget to 0.

## Conservation
- **Firms (T6 group):** Potential Customers + Firms in Evaluation + Customers + Cooling Off Firms + Firms Yet To
  Enter = initial total market + initial firms yet to enter, constant at all times. Every firm flow leaves one of
  these stocks and enters another; market entries move firms from Firms Yet To Enter into the pool. Market entries stop at the
  market growth horizon (120 months), when Firms Yet To Enter reaches exactly 0, so the source never goes negative.
  At the default market growth of 0 this is the worked example's closed market.
- **Money (checked at gate 5 as an extreme-case expectation):** Cumulative Programme Spend at month 60 = total
  programme budget, in every scenario.
- **ARR identity (separate check, gate 1):** with base net expansion = 0 and parameter A = 0,
  ARR = Customers x new customer ACV at every step. It holds by construction: both start equal, and
  d(ARR)/dt = ACV x (deals won - churn) = ACV x d(Customers)/dt.
- **Not conserved, by design:** Recently Churned Firms (information), CS Capacity and Win Rate Capability
  (resources that goal-seek toward what the budget funds), Cumulative Revenue and Cumulative Programme Spend
  (accumulators).

## Delays (explicit stocks, all first order)
Sales cycle (Firms in Evaluation), cool-off (Cooling Off Firms), detractor memory (Recently Churned Firms), CS
ramp-up (CS Capacity) and enablement ramp-up (Win Rate Capability). Longest in the expected ranges: cool-off, up to
36 months; the 120-month horizon is >= 3x that (gate 1).

## Regression mapping to `bass-b2b-adoption` (gate 1 check)
With total budget = 0, A = B = C = 0, base net expansion = 0, market growth = 0 and initial sales capacity far above
any deal flow, every added term is exactly neutral. MAX(0, customer share - 0) = customer share; MIN(E / sales cycle,
capacity) = E / sales cycle; effective win rate = base win rate; churn reduction = 0; total market = initial total
market. Customers should therefore match the example step for step at the same time step; the check reports the
maximum absolute difference.

## Changes from gate 3 (no loop changes)
- Cumulative Market Entries is replaced by the source stock **Firms Yet To Enter**, because T6 sums stocks and needs a
  constant total. It has no incoming dynamic links, so the 21 declared loops are unchanged.
- Budget as a share of ARR (gate 1 sensitivity) would make spend depend on ARR. That creates new loops, which T8
  would flag in this model even when switched off. It therefore runs as a **separate variant model** at gate 8,
  not as a switch in this one.

## Policy comparison (decided at gate 4 approval)
`engine/validate.py` measures every policy's gain, per sample, against the **first** policy in `[[policies]]`, and
takes the Monte Carlo bands (fan chart) from that scenario too. **"No programme" is listed first** (no engine
change). Gains and ranking stability (T7b) are therefore per sample against the unfunded baseline, on common random
numbers. The bands in `mc_bands.csv` show the no-programme world. The funded scenarios' bands come from separate
runs at gate 8 with the same samples and seed. The base parameter set stays the 50/50 split (gate 3), so the base,
dt-halving, extreme and T8 runs exercise every loop.

## Amendment 2026-10-29 (gate 5 approval)
| Variable | Equation | Unit |
|---|---|---|
| ARR per customer | ARR / MAX(Customers, minimum customer base) | USD/(Firm*Year) |
| expansion headroom | 1 - ARR per customer / (new customer ACV x expansion ceiling multiple) | Dmnl |
| expansion ARR (replaces the row above) | ARR x effective expansion rate monthly x expansion headroom | USD/(Year*Month) |
| CS coverage (renamed constant) | CS Capacity / MAX(Customers, minimum customer base) | Dmnl |

Why ARR per customer cannot pass the ceiling: churned ARR removes the same fraction of ARR as churn removes of
Customers, so churn leaves the average unchanged. New ARR enters at ACV, at or below the average, and expansion goes
to 0 as the average approaches ACV x multiple. Euler keeps this bound while effective expansion rate monthly x dt < 1
(it is <= 1/12 x 0.25 at the domain maximum). Two extreme cases in `validation.toml` check it. The ARR identity check
is unaffected (expansion = 0), and so is the regression (ARR feeds nothing that reaches Customers). Loops: 22 (gate 3
amendment).
