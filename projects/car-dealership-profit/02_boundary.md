# Gate 2: Model boundary

Baseline: one single-location franchised US new-car dealer. Delays (lease term, reconditioning, hiring) are written as
explicit stocks at gate 4; they are listed here as stocks only to mark them endogenous.

| Variable | Status | Justification |
|---|---|---|
| Prospects in market | endogenous (stock) | demand pool fed by marketing and market entry, drained by purchases; sets the ceiling on sales |
| New-car owners, used-car owners | endogenous (stocks) | installed base; their ownership clock drives repeat purchase and service |
| Lessees (as a pipeline of explicit stages for the lease term) | endogenous (stocks) | lease volume now becomes off-lease supply and a repeat-buy decision about 36 months later (gate 1 hypothesis 3) |
| Service customer base | endogenous (stock) | owners and lessees who use this store's service; filled by sales, drained by defection and aging out |
| New-vehicle inventory | endogenous (stock) | refilled by manufacturer allocation orders, drained by sales; carrying cost through floorplan |
| Used-vehicle inventory, reconditioning pipeline | endogenous (stocks) | refilled by trade-ins, auction buys and off-lease returns; drained by retail sales and wholesale exits; reconditioning is an explicit stage |
| Aged-inventory discounting | endogenous | days-supply above target pushes price down and raises wholesale exits (balancing loop, gate 1 hypothesis 6) |
| F&I income, chargebacks | endogenous | F&I product per retail unit = penetration x product gross; chargebacks from early cancellations reduce it |
| Technician headcount, effective service capacity | endogenous (stock) | hired with a delay toward a target set by the capital-allocation lever; capacity caps repair orders |
| Repair orders and parts sales | endogenous | demand from the service customer base, limited by capacity |
| Floorplan debt | endogenous (stock) | finances inventory at cost; interest is a cost line |
| Cash, cumulative net profit | endogenous (accumulators) | cumulative net profit before tax is the objective; cash tracks it with working capital |
| Absorption rate | endogenous | fixed-ops gross / fixed overhead; resilience indicator (lens B) |
| Capital allocation schedule per scenario | exogenous | the lens A decision variable; same dollars in every scenario |
| Target business mix (used-heavy, lease-heavy, fixed-ops-heavy) | exogenous | the lens C decision variable |
| Shocks: new-vehicle gross, floorplan rate, demand spell | exogenous | the lens B inputs, applied one at a time and combined |
| Manufacturer allocation (new-vehicle supply) | exogenous | base value fixed; response to the store's own sales is an optional parameter C |
| Interest rate (floorplan and consumer finance), auction price level, residual values set at lease origination | exogenous | macro and market prices the store takes as given; a single store does not move them |
| Base gross per unit: new, used; F&I product gross; gross per repair order | exogenous | benchmark ranges, `estimated` or `reported` at gate 5 |
| Fixed overhead, commission rates, technician wage | exogenous | cost parameters; overhead includes a normal management salary for the owner |
| Discount rate | exogenous | lens D parameter, base and range at gate 5; a stated parameter, not a finding |
| Service retention rate | exogenous | base rate; wait-time effect on retention is optional parameter A |
| Marketing effect per dollar, diminishing-returns shape | exogenous | response curve; `estimated`, wide range |
| Manufacturer incentives, holdback, factory bonuses | excluded | folded into base new-vehicle gross per unit, so its range includes them; no separate feedback |
| Multi-rooftop groups, shared services, acquisitions | excluded | baseline is one store |
| Body shop, wholesale parts to other shops | excluded | a different business line; fixed ops here means customer-pay, warranty and internal repair plus counter parts |
| Dealer-owned reinsurance and warranty-claim risk | excluded | the store sells third-party contracts and keeps commission; claim cost sits with the administrator |
| Income tax, real-estate ownership, financing of the store itself | excluded | objective is pre-tax profit; rent is inside overhead |
| EV transition and direct (agency) sales | excluded | structural change outside the 5- to 10-year decision window of lenses A to C; see limit 6 |
| Customer segments, brand mix, trim-level mix | excluded | one homogeneous customer and vehicle mix |

## Optional sensitivity parameters (default 0; ranges set and sourced at gate 5, tag `estimated`)
They let the largest omissions be sensitivity-tested without a boundary change. At the default every one is off.

| ID | Parameter | Unit | Stands in for excluded feedback | Structural note |
|---|---|---|---|---|
| A | Retention loss when service demand exceeds capacity | Dmnl | 2 (long waits -> fewer returning customers) | adds a balancing loop (service customer base -> repair order demand -> capacity utilisation -> retention -> service customer base). The link exists at every value, so the loop is declared at gate 3 and checked by T8 even at the default |
| B | Floorplan credit limit as a multiple of baseline inventory value | Dmnl | 3 (cash and credit -> inventory depth) | binding limit on inventory purchases; no new loop, exogenous cap. Default: non-binding |
| C | Allocation response to the store's trailing new-vehicle sales | Dmnl | 4 (sales performance -> manufacturer allocation) | adds a reinforcing loop (new sales -> allocation -> new inventory -> new sales). The link exists at every value, so the loop is declared at gate 3 and checked by T8 even at the default |

## Excluded feedbacks likely to matter, and what they bias
These go word for word into the **Model limits** section of `summary.md` at gate 9. Each direction is for that item
alone, at the default of its sensitivity parameter where one exists.

| # | Excluded or simplified feedback | What excluding it does | Bias favours | Sensitivity parameter |
|---|---|---|---|---|
| 1 | Price and discount -> demand elasticity for new cars | A margin squeeze cuts gross per unit with no volume gain, and a lever that buys volume with price gets no credit | **fixed-ops-heavy and F&I options** (new-car shock looks worse than it is) | none |
| 2 | Service waits and quality -> retention | Fixed ops growth is never choked by its own congestion; capacity shortfalls cost nothing beyond lost repair orders | **service capacity investments (lens A) and fixed-ops-heavy mix (lens C)** | A |
| 3 | Credit and cash -> inventory depth | Inventory investment is never limited by the credit line | **used-inventory investments (lens A) and used-heavy mix (lens C)** | B |
| 4 | Sales performance -> manufacturer allocation | New supply stays fixed, so a store that sells more new cars gains no extra supply | **non-new-car options** | C |
| 5 | Competitor response (price, service offers) | Gains from any lever last as long as the spend | **all options, most where competition is closest (service, used)** | none |
| 6 | EV transition and direct sales | Service demand per car and new-car margin stay as in the baseline | **fixed-ops-heavy mix (lens C) and lens D valuation** (durability of service profit overstated) | none |

**Net direction and size of these biases are unquantified.** The items differ in size, so how many point each way
says nothing about the net effect. Gate 8 reports how far A, B and C move the rankings across their ranges. Items
1, 5 and 6 remain untested by parameters and stay listed as limits.
