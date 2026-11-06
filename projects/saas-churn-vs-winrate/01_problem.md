# Gate 1: Problem articulation

**Question (as given):** "Should we fund churn reduction or a higher win rate first over the next 5 years, and what limits growth?"

**Decision the model informs.** How to sequence one fixed 5-year programme budget between a churn-reduction
programme (customer success) and a win-rate programme (sales enablement), judged by **ARR at month 60**; and what
ARR range to plan for under each sequence. Scenarios, all with the **same total dollars**:
1. churn first: months 0-24 churn programme, months 24-60 win-rate programme
2. win rate first: the reverse
3. 50/50 split for all 60 months
4. churn only
5. win rate only
(plus "no programme" as the baseline).

**Context (assumed, confirmed by the user):** generic mid-market B2B SaaS, sales-led evaluation, identifiable
target market; parameters from published benchmark ranges (tagged `reported` / `estimated` at gate 5), not from one
company's data. The customer structure reuses this repo's own `projects/bass-b2b-adoption` model (Bass demand,
sales pipeline, churn, cool-off), extended with money and capacity.

## Key variables
| Variable | Unit | Role |
|---|---|---|
| Customers | Firm | logo base |
| ARR (own stock: new ARR in, expansion in, churned ARR out) | USD/Year | **objective at month 60** |
| New-customer ACV | USD/(Firm*Year) | revenue per new logo |
| Net expansion rate | 1/Year | separate parameter from ACV |
| Cumulative revenue, months 0-60 | USD | second output, non-gating |
| Firms in Evaluation; evaluation starts, deals won, churn | Firm; Firm/Month | pipeline and attrition |
| Win rate; monthly churn fraction | Dmnl; 1/Month | the two levers' targets |
| Total programme budget | USD | fixed per scenario; base and range at gate 5 |
| Churn programme spend; win-rate programme spend | USD/Month | dollar schedule set by the scenario |
| Programme capability (one explicit stock per programme) | Dmnl | ramp-up delay between spend and effect |
| Effect per dollar, diminishing-returns shape, ramp-up time | per lever | response curves, all `estimated`, wide ranges |
| Sales capacity; customer-success capacity | Firm/Month; Firm | candidate growth limits |
| Market growth rate | 1/Year | base 0; range at gate 5 |

Unit conversion stated now: ARR is USD/Year and the model runs in Months, so
cumulative revenue = INTEG(ARR / months per year), with `months per year` = 12 Month/Year as a named constant
(USD/Year / (Month/Year) = USD/Month, integrated over Month = USD).

## Outputs the model must produce
- ARR at month 60 by scenario (P5-P95, P25-P75, median), and ranking stability (T7b).
- Cumulative revenue over months 0-60 by scenario (non-gating).
- **Break-even relative cost-effectiveness**: the ratio (win-rate effect per $) / (churn effect per $) at which the
  ranking of "churn first" vs "win rate first" flips, with its band across the Monte Carlo samples.
- **Net-of-cost comparison vs the no-programme baseline:** ARR lift at month 60 per dollar of budget
  ((ARR_scenario - ARR_baseline) / total budget, unit 1/Year), and cumulative revenue minus programme spend over
  months 0-60 minus the baseline's cumulative revenue (USD).
- Budget as a share of ARR instead of a fixed schedule: **sensitivity run only**, not a scenario.
- Which loop or constraint limits growth, by period (loop dominance + Spearman table).

## Checks required beyond the standard T0-T8
- **Regression vs the worked example:** spend = 0, expansion = 0, constant ACV, market growth = 0, sales and
  customer-success capacity set non-binding, same base parameters as `bass-b2b-adoption` -> the Customers
  trajectory reproduces `projects/bass-b2b-adoption` (max absolute difference reported; target ~1e-9).
- **ARR identity:** with expansion = 0, ARR = Customers x ACV at every step (relative error < 1e-6).
- Neither is native to `engine/validate.py`. How they run (project script vs engine change) is set at gate 5; any
  engine change needs user approval first.

## Time horizon
120 months; decision horizon 60. Longest delay in the expected ranges is the 36-month cool-off of lost and churned
firms (programme ramp-up is expected at 6-12 months), so horizon >= 3 x 36 = 108 months
(`library/modeling_checklist.md` item 1). The 60 months after the budget ends show whether a lever's gain persists.

## Reference modes
- **Historical: none.** Generic benchmarks; no data is invented. T5 uses the analytic Bass limit case, as the
  worked example does.
- **Expected behavior over time (hypotheses stated before any run, not results):**
  1. Customers and ARR are S-shaped; ARR rises faster than logos when net expansion > 0.
  2. Win-rate spend acts sooner (every deal, plus word of mouth) but may hit the sales-capacity ceiling.
  3. Churn spend acts with a lag and compounds through a larger base and expansion revenue; its value rises with
     time, expansion and ACV.
  4. The binding limit shifts over time (demand and pipeline early; capacity or churn later). The model, not this
     guess, decides.
  5. With market growth > 0 the saturation ceiling moves up; at base (0) the market is closed.

## Settled at gate 1 approval (carried into gate 2)
- Customer-success capacity is a **stock** (it limits how many customers the churn programme can reach).
- Price changes stay **excluded**; expansion covers upsell only.

## Amendment 2026-10-29 (gate 5 approval; before any model run)
**Replaces expected behavior 1 for ARR.** Expected behavior 1 said ARR is S-shaped. It is replaced by: ARR =
Customers x average ARR per customer. Customers are expected to follow an S-curve. Average ARR per customer is
expected to rise from the new-customer ACV toward a ceiling (`expansion ceiling multiple` x ACV, added at gate 5),
pulled down by new logos joining at ACV. Whether ARR looks S-shaped, exponential or near-linear inside 120 months
depends on uncertain parameters, so **no behavior mode is declared for ARR** (T5 checks modes for Customers and
customer share only). Reason: the gate 5 structure (net expansion above churn, then an expansion ceiling) does not
determine the shape; stating one would be a guess.
