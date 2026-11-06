# Gate 1: Problem articulation

**Question (as given):** "How does a traditional car dealership make money (new cars, used cars, leases, service and parts, warranties/F&I), and what levers drive profit over time?"

**Baseline (confirmed by the user):** one single-location, franchised, US new-car dealer. Parameters come from published
industry benchmark ranges (tagged `reported` / `estimated` at gate 5), not from one dealership's books. Nothing in this
file is a result; every number-shaped statement below is a hypothesis to be tested, tagged `[unverified]`.

## Decisions the model informs (one model, four lenses, same baseline dealership)
| Lens | Decision | Scenarios (equal-sized lever changes unless noted) | Judged by |
|---|---|---|---|
| A. Capital allocation | Where does the next block of dollars go? | Same dollars into: used-car inventory depth, service capacity (technicians and bays), F&I staff and product, or marketing/lead generation | Cumulative net profit months 0-60, payback month, profit per dollar invested |
| B. Resilience | How exposed is profit to a new-car margin squeeze, and can service and F&I cover the gap? | Shocks, one at a time and combined: new-vehicle gross per unit down, floorplan interest rate up, demand down for a stated spell | Lowest monthly net profit, share of Monte Carlo samples with a cumulative loss, months of the shock during which fixed-ops gross covers fixed overhead |
| C. Strategy | Which business mix should the store lean toward? | Mix targets with the same capital: used-heavy, lease-heavy, fixed-ops-heavy, vs baseline mix | Cumulative net profit and downside (P5) by mix |
| D. Buying or valuing | What is the store worth, and what range of cash flows sits behind a price? | No lever. Reads the baseline and the scenarios as cash flow | Discounted net cash flow, months 0-120, as bands |

Lenses A to C use the model's levers; D is an output lens on the same runs. A, B and C are compared on the common
metric **cumulative net profit before tax** so their answers stay comparable.

## Key variables
| Variable | Unit | Role |
|---|---|---|
| Prospects in market (customers considering a purchase) | Customer | demand pool feeding all sales lines |
| Customers by state: new-car owners, lessees, used-car owners | Customer | installed base; their replacement cycle drives repeat sales and service |
| New-vehicle inventory; used-vehicle inventory | Vehicle | stocks that sales draw down and sourcing refills |
| New-vehicle supply (allocation from the manufacturer) | Vehicle/Month | exogenous cap on new sales |
| Used-vehicle sourcing: trade-ins, auction purchases, off-lease returns | Vehicle/Month | refills used inventory; off-lease returns arrive 36 months after leases start |
| Reconditioning pipeline | Vehicle | explicit stock between acquisition and frontline-ready |
| Gross profit per unit: new, used, F&I per retail unit | USD/Vehicle | margin of each sales line |
| F&I penetration (share of retail units with a contract) | Dmnl | multiplies F&I product per unit |
| Lease residual risk (residual value vs resale price) | USD/Vehicle | gain or loss when an off-lease car is remarketed |
| Service customer base; repair orders | Customer; RO/Month | fixed-ops demand |
| Technician headcount and effective bay capacity | Person; RO/Month | fixed-ops supply ceiling |
| Gross profit per repair order: customer-pay, warranty, parts | USD/RO | fixed-ops margin |
| Fixed overhead; variable selling expense (commissions) | USD/Month; USD/Vehicle | cost side |
| Floorplan debt and interest rate | USD; 1/Month | financing cost on inventory |
| Cash | USD | accumulates net profit; working capital sits in inventory |
| **Objective: cumulative net profit before tax** | USD | months 0-60 (decision), months 0-120 (valuation lens) |
| Absorption rate: fixed-ops gross / total fixed overhead | Dmnl | resilience indicator (lens B) |

Unit conversions to be named constants: `months per year` = 12 Month/Year, `days per month` (days-supply of
inventory). Vehicles and customers are whole units modeled as continuous (stated in the model notes).

## Outputs the model must produce
- Cumulative net profit by scenario for each lens (P5-P95, P25-P75, median), and ranking stability (T7b).
- Profit decomposition by line over time: new, used, lease remarketing, F&I, service, parts, less overhead and floorplan.
- Resilience metrics under each shock (lens B), and mix comparison with downside (lens C).
- Discounted net cash flow bands (lens D); discount rate is a stated parameter with a range, not a finding.
- Which loop or constraint limits profit, by period (loop dominance plus Spearman table).

## Checks required beyond the standard T0-T8
- **Vehicle conservation:** vehicles acquired = vehicles sold + change in inventory and reconditioning stocks (relative drift < 1e-6), for new and used separately.
- **P&L identity:** net profit = sum of line gross profits - overhead - floorplan interest - variable selling expense, at every step (relative error < 1e-6).
- **Cash identity:** cash change = net profit + change in floorplan debt - change in inventory value - dealer-funded investment spend.
- **Limit case:** leases = 0, F&I = 0, service = 0 -> the dealership reduces to a new-and-used unit seller; its inventory behavior matches the stock-management archetype in `library/archetypes.md` (checked at gate 7).
- Neither identity is native to `engine/validate.py`; how they run (project `checks.py`, as `saas-churn-vs-winrate` does) is set at gate 5. Any engine change needs your approval first.

## Time horizon
**180 months** (15 years); decision horizon 60 months (lenses A to C), valuation horizon 120 months (lens D).
Longest delay in the expected ranges: the customer replacement cycle, about 36-72 months `[unverified]` (lease term
about 36 months, then remarketing; ownership cycle for purchases longer). Horizon >= 3 x 60 = 180 months
(`library/modeling_checklist.md` item 1). The echo of today's lease and new-car sales into used supply and service
demand years later is the dynamic the lenses depend on.

## Reference modes
- **Historical: none.** No dealership data is invented. T5 uses an analytic limit case, as the worked examples do (the inventory-with-delay archetype: goal-seeking inventory under constant demand).
- **Expected behavior over time (hypotheses stated before any run, not results):**
  1. New-vehicle sales are most of revenue but a minority of gross profit; fixed ops (service and parts) is a small share of revenue and a large share of gross `[unverified]`. The model should show this mix emerging, not have it set in.
  2. Used inventory follows a stock-management pattern: sourcing adjusts toward a target days-supply with a delay, so demand shocks cause a hump then undershoot.
  3. Lease volume echoes: a rise in leases now raises off-lease used supply and service traffic about 36 months later, with remarketing gain or loss depending on residual value risk.
  4. Service gross compounds slowly with the owner base (a reinforcing loop through customer retention) and is capped by technician and bay capacity.
  5. Under a new-car margin squeeze, profit falls less than the new-car loss only to the extent the absorption rate is near or above 1. The model decides how far it holds.
  6. Floorplan interest turns slow-moving inventory into a drag (a balancing loop through carrying cost and discounting).

## Open points for your approval
- Objective for all lenses: cumulative net profit **before tax** (tax excluded). Alternative: after tax. Recommended: before tax; tax is a rate on the result and adds no feedback.
- Horizon 180 months, decision horizon 60. Longer than the SaaS examples because of the replacement-cycle delay.
- Scale of the baseline store (units per year) is a gate 5 parameter, not set here.
