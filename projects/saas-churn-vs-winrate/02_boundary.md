# Gate 2: Model boundary

| Variable | Status | Justification |
|---|---|---|
| Potential Customers, Firms in Evaluation, Customers, Cooling Off Firms | endogenous (stocks) | core adoption, pipeline and churn structure, reused from `bass-b2b-adoption` |
| ARR | endogenous (stock) | objective; fed by new ARR and expansion, drained by churned ARR |
| Cumulative revenue (0-60) | endogenous (accumulator) | second output; INTEG(ARR / months per year) |
| Cumulative programme spend | endogenous (accumulator) | needed for the net-of-cost comparison |
| Customer-success capacity | endogenous (stock) | built by churn-programme spend with a ramp-up delay; its coverage of Customers sets the churn reduction (approved at gate 1) |
| Win-rate programme capability | endogenous (stock) | built by win-rate spend with a ramp-up delay, decays without spend; sets the win-rate uplift |
| Effective win rate, effective churn fraction | endogenous | base value modified by the programmes, with diminishing returns |
| Effective net expansion rate | endogenous | base net expansion rate + optional lift from churn-programme capability (optional parameter A) |
| Word-of-mouth starts | endogenous | Bass word of mouth from Customers, reduced by recently churned firms when optional parameter C > 0 |
| Recently churned firms (detractor pool) | endogenous (stock) | filled by churn, drained over a detractor memory time; needed only for parameter C, inactive at its default |
| Deals won limited by sales capacity | endogenous (constraint) | lets the model show when capacity, not demand, limits growth |
| Market growth inflow to Potential Customers | endogenous flow, exogenous rate | base rate 0; conservation counts cumulative market entries |
| Total programme budget and its monthly schedule per scenario | exogenous | the decision variable; same total in every scenario |
| Sales capacity (deals/Month) | exogenous | initial value plus optional exogenous growth (optional parameter B); not driven by revenue |
| New-customer ACV, base net expansion rate | exogenous | benchmark ranges; kept separate (gate 1) |
| ARR per customer, expansion headroom | endogenous | expansion slows as average ARR per customer approaches the ceiling (added at gate 5) |
| Expansion ceiling multiple | exogenous | ceiling on average ARR per customer as a multiple of ACV; range 1.3-4.0 (gate 5) |
| Bass reach and word-of-mouth rates, base win rate, base churn, sales cycle, cool-off time | exogenous | same roles and ranges as the worked example unless gate 5 says otherwise |
| Effect per dollar, diminishing-returns shape, ramp-up and decay times, cost per CS seat | exogenous | response curves; `estimated`, wide ranges; break-even ratio output covers this uncertainty |
| Market growth rate | exogenous | base 0, ranged at gate 5 |
| Price changes | excluded | user decision at gate 1; expansion covers upsell only |
| Competitors and their response | excluded | no data; win rate and churn baselines treated as fixed |
| Product quality and roadmap | excluded | outside a 5-year programme budget decision |
| Customer segments (SMB vs enterprise) | excluded | one homogeneous segment, as in the worked example |
| Discounting / NPV | excluded | objective is ARR at month 60 and undiscounted cumulative revenue net of spend |

## Optional sensitivity parameters (default 0; ranges set and sourced at gate 5, tag `estimated`)
They let the largest omissions be sensitivity-tested without a boundary change. At the default every one is off,
so the base case matches the exclusions listed below.

| ID | Parameter | Unit | Stands in for excluded feedback | Structural note |
|---|---|---|---|---|
| A | Expansion lift from churn-programme capability | 1/Year | 2 (CS -> expansion) | adds a link, no new loop: ARR does not feed back into the budget or capability |
| B | Sales capacity growth rate | 1/Year | 1 (revenue -> hiring -> sales capacity), as a time-driven proxy | exogenous growth, not driven by revenue, so it adds no feedback loop. Formula vs stock is settled at gate 4; if a stock is used, its self-loop is declared at gate 3 |
| C | Negative word-of-mouth multiplier on recently churned firms | Dmnl | 3 (churned customers -> negative word of mouth) | adds a balancing loop (Customers -> churn -> recently churned firms -> fewer word-of-mouth starts -> fewer deals won -> Customers). The link exists at every value, so the loop is declared at gate 3 and checked by T8 even at the default |

Regression test against `bass-b2b-adoption` (gate 1): A = B = C = 0, along with spend = 0, expansion = 0, market
growth = 0 and capacity non-binding.

## Excluded feedbacks likely to matter, and the direction of bias
These five go word for word into the **Model limits** section of `summary.md` at gate 9. Each direction is for that
item alone, at the default of its sensitivity parameter where one exists.

| # | Excluded feedback | What excluding it does | Bias favours | Sensitivity parameter |
|---|---|---|---|---|
| 1 | Revenue -> hiring -> sales capacity | Sales capacity stays fixed, so it binds more often than it would; caps the win-rate programme's gains, mostly late | **churn programme** | B (time-driven proxy) |
| 2 | Customer success -> expansion | Churn spend gets no credit for upsell | **win-rate programme** | A |
| 3 | Churned customers -> negative word of mouth | Cutting churn gets no credit for protecting acquisition | **win-rate programme** | C |
| 4 | Competitor response to a higher win rate | The win-rate gain lasts as long as the spend instead of eroding | **win-rate programme** | none |
| 5 | ARR -> programme budget (reinvestment) | No compounding budget for the lever that raises ARR sooner. Gate 1 hypothesis 2 expects that is the win-rate programme; if gates 7-8 show the opposite, the direction flips and the summary will say so | **churn programme** (conditional on hypothesis 2) | none; budget as a share of ARR is the gate 1 sensitivity run |

**Net direction and size of these biases are unquantified.** The items differ in size, so how many point each way
says nothing about the net effect. Gate 8 reports how far A, B and C move the ranking across their ranges. Items 4
and 5 remain untested by parameters and stay listed as limits.

## Amendment 2026-10-29 (gate 5 approval): expansion ceiling and a sixth limit
The expansion ceiling is inside the model, but it simplifies the real tenure structure. It is added to the limits
that go word for word into **Model limits** in `summary.md`:

| # | Simplification | What it does | Bias favours | Sensitivity parameter |
|---|---|---|---|---|
| 6 | Expansion capped on **average** ARR per customer, with no cohorts or tenure | New logos join at ACV, lower the average and reopen expansion headroom for the whole base; customers kept by the churn programme fill the ceiling instead | **win-rate programme** | expansion ceiling multiple (range 1.3-4.0) |

Net direction and size across all six remain unquantified.
