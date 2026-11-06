# Gate 4: Stock-flow structure

Time unit: **Month**. Annual rates are converted with the named constant `months per year` = 12 Month/Year, days with
`days per month`, and a household purchase becomes a vehicle with `vehicles per household purchase` (Vehicle/Household),
never a bare number (`library/units.md` rule 4). Every delay is an explicit stock (no SMOOTH/DELAY). Functions used are
limited to those T1 can check: `IF THEN ELSE`, `MIN`, `MAX`, `EXP`, `Time`. Literal numbers are only 0 and 1.
Parameter values, ranges and sources come at gate 5. Vehicles and households are counted in whole units but modeled
as continuous.

This table and the equations below were checked against the causal loop diagram by script: every dependency among
CLD variables in the equations is a CLD link and the reverse. That turned up two amendments to gate 3 (see
`03_dynamic_hypothesis.md`, bottom): 67 loops, not 48. One of them corrects an error of mine: a loop with no stock in it
(an algebraic loop). Both are proposed for your approval together with this gate.

## Stocks

| # | Stock | Unit | Initial value | Inflows | Outflows | Kind |
|---|---|---|---|---|---|---|
| 1 | Prospects | Household | initial prospects | market entries + marketing starts + repeat to store | new sales + used sales | material |
| 2 | Owners | Household | initial owners | retail new buys + used sales | replacement | material (ownership period) |
| 3 | Lessees Early | Household | initial lessees per stage | lease starts | lease advance 1 | material (lease stage 1) |
| 4 | Lessees Mid | Household | initial lessees per stage | lease advance 1 | lease advance 2 | material (lease stage 2) |
| 5 | Lessees Late | Household | initial lessees per stage | lease advance 2 | lease end | material (lease stage 3) |
| 6 | Households Elsewhere | Household | 0 | leakage | none | material sink (bought or leased at other stores) |
| 7 | Households Outside Market | Household | (market entry rate + maximum marketing starts) * simulation horizon | none | market entries + marketing starts | material source |
| 8 | New Inventory | Vehicle | initial new inventory | deliveries | new sales * vehicles per household purchase | material |
| 9 | New Vehicles On Order | Vehicle | initial new vehicles on order | new orders | deliveries | material (order lead time) |
| 10 | Used Frontline Inventory | Vehicle | initial used frontline inventory | recon done | used sales * vehicles per household purchase + wholesale exits | material |
| 11 | Reconditioning Pipeline | Vehicle | initial reconditioning pipeline | used acquisitions | recon done | material (reconditioning time) |
| 12 | Manufacturer Supply Outside | Vehicle | manufacturer allocation * simulation horizon | none | new orders | material source (bounded by the allocation cap) |
| 13 | New Vehicles Sold | Vehicle | 0 | new sales * vehicles per household purchase | none | material sink |
| 14 | Used Vehicle Supply Outside | Vehicle | initial used supply outside | none | used acquisitions | material source |
| 15 | Used Vehicles Sold On | Vehicle | 0 | used sales * vehicles per household purchase + wholesale exits | none | material sink |
| 16 | Trailing New Sales | Household/Month | reference new sales | trailing change | none | information (allocation memory) |
| 17 | Trailing Used Sales | Household/Month | reference used sales | trailing used change | none | information (used sales memory) |
| 18 | Service Customers | Household | initial service customers | service capture | defection | material subset of the customer base |
| 19 | Technicians | Technician | initial technicians | hiring | attrition | resource (hiring delay) |
| 20 | Inventory at Cost | USD | initial inventory at cost | deliveries * new vehicle unit cost + used acquisitions * used vehicle unit cost | inventory cost released | money (valued at unit cost) |
| 21 | Floorplan Debt | USD | initial floorplan debt | advance rate * (deliveries * new vehicle unit cost + used acquisitions * used vehicle unit cost) | floorplan payoff | money |
| 22 | Cash Received | USD | 0 | MAX(0, net cash flow) | none | accumulator (non-negative part of cash flow) |
| 23 | Cash Paid Out | USD | 0 | MAX(0, 0 - net cash flow) | none | accumulator (non-negative part of cash flow) |
| 24 | Cumulative Profit Earned | USD | 0 | MAX(0, net profit) | none | accumulator (non-negative part of net profit) |
| 25 | Cumulative Loss Incurred | USD | 0 | MAX(0, 0 - net profit) | none | accumulator (non-negative part of net profit) |
| 26 | Cumulative Discounted Cash Received | USD | 0 | MAX(0, discounted net cash flow) | none | accumulator (non-negative part) |
| 27 | Cumulative Discounted Cash Paid | USD | 0 | MAX(0, 0 - discounted net cash flow) | none | accumulator (non-negative part) |

**Initial values.** The `initial ...` constants are the **base-parameter steady state**, solved by `settle.py` (an
independent Euler mirror of these equations in `model_spec.py`; the numbers come from running it, not from assumption; they are listed in `assumptions_register.md`), so the base run starts in
equilibrium and any movement is caused by a lever or shock. `Households Outside Market` and `Manufacturer Supply
Outside` are sized as rate x `simulation horizon` so the source stocks can never go negative. `Used Vehicle Supply
Outside` is a large constant that T3 checks stays non-negative. Cash, floorplan debt and inventory at cost start
consistent: floorplan debt = `advance rate` x inventory at cost.

## Auxiliaries and flows

| Variable | Equation | Unit |
|---|---|---|
| shock active | IF THEN ELSE(Time >= shock start month, IF THEN ELSE(Time < shock start month + shock duration, 1, 0), 0) | Dmnl |
| shoppers | Prospects * shopping rate monthly * (1 - demand shock size * shock active) | Household/Month |
| new demand | shoppers * new share of shoppers | Household/Month |
| used demand | shoppers * (1 - new share of shoppers) * (1 + discount demand sensitivity * used price discount) | Household/Month |
| new sales | MIN(new demand * New Inventory / (New Inventory + availability constant new), New Inventory / (minimum sellout time * vehicles per household purchase)) | Household/Month |
| used sales | MIN(used demand * Used Frontline Inventory / (Used Frontline Inventory + availability constant used), Used Frontline Inventory / (minimum sellout time * vehicles per household purchase)) | Household/Month |
| lease starts | new sales * lease share | Household/Month |
| retail new buys | new sales * (1 - lease share) | Household/Month |
| lease stage time | lease term / number of lease stages | Month |
| lease advance 1 | Lessees Early / lease stage time | Household/Month |
| lease advance 2 | Lessees Mid / lease stage time | Household/Month |
| lease end | Lessees Late / lease stage time | Household/Month |
| replacement | Owners / ownership period | Household/Month |
| service ratio | Service Customers / MAX(Owners, minimum owner base) | Dmnl |
| store loyalty | loyalty floor + (loyalty ceiling - loyalty floor) * service ratio / (service ratio + loyalty half saturation) | Dmnl |
| repeat to store | (replacement + lease end) * store loyalty | Household/Month |
| leakage | replacement + lease end - repeat to store | Household/Month |
| marketing starts | maximum marketing starts * (1 - EXP(-marketing spend / marketing spend scale)) | Household/Month |
| market entries | market entry rate | Household/Month |
| trade ins | replacement * trade in share * vehicles per household purchase | Vehicle/Month |
| off lease returns | lease end * off lease return share * vehicles per household purchase | Vehicle/Month |
| target used inventory | used sales * vehicles per household purchase * (target used days supply / days per month + reconditioning time) | Vehicle |
| auction buys | MAX(0, used sales * vehicles per household purchase + (target used inventory - Used Frontline Inventory - Reconditioning Pipeline) / used inventory adjustment time - trade ins - off lease returns) | Vehicle/Month |
| used acquisitions | trade ins + off lease returns + auction buys | Vehicle/Month |
| recon done | Reconditioning Pipeline / reconditioning time | Vehicle/Month |
| trailing used change | (used sales - Trailing Used Sales) / used sales memory | Household/Month/Month |
| used days supply | Used Frontline Inventory / MAX(Trailing Used Sales * vehicles per household purchase, minimum used sales rate) * days per month | Day |
| used price discount | MIN(maximum price discount, discount sensitivity * (used days supply - target used days supply) / target used days supply) | Dmnl |
| wholesale exits | Used Frontline Inventory * wholesale exit rate monthly * used days supply / target used days supply | Vehicle/Month |
| target new inventory | new sales * vehicles per household purchase * (target new days supply / days per month + order lead time) | Vehicle |
| allocation response | allocation response strength * (Trailing New Sales / reference new sales - 1) | Dmnl |
| new orders | MIN(manufacturer allocation, MAX(0, (new sales * vehicles per household purchase + (target new inventory - New Inventory - New Vehicles On Order) / new inventory adjustment time) * (1 + allocation response))) | Vehicle/Month |
| deliveries | New Vehicles On Order / order lead time | Vehicle/Month |
| trailing change | (new sales - Trailing New Sales) / allocation memory | Household/Month/Month |
| service capture | (new sales + used sales) * service capture share | Household/Month |
| capacity | Technicians * repairs per technician | RO/Month |
| ro demand | Service Customers * visits per customer monthly | RO/Month |
| utilisation | ro demand / capacity | Dmnl |
| defection | Service Customers * base defection rate monthly * (1 + retention loss when overloaded * (utilisation - 1)) | Household/Month |
| ro done | MIN(ro demand, capacity) | RO/Month |
| hiring | (technician target - Technicians) / hire time | Technician/Month |
| attrition | Technicians * attrition rate monthly | Technician/Month |
| inventory cost released | new sales * vehicles per household purchase * new vehicle unit cost + (used sales * vehicles per household purchase + wholesale exits) * used vehicle unit cost | USD/Month |
| floorplan payoff | advance rate * inventory cost released | USD/Month |
| margin shock factor | 1 - margin shock size * shock active | Dmnl |
| new gross | new sales * vehicles per household purchase * new gross per vehicle * margin shock factor | USD/Month |
| used gross | used sales * vehicles per household purchase * (used gross per vehicle - used price discount * used retail price) | USD/Month |
| lease remarketing gain | 0 - off lease returns * lease remarketing loss per vehicle | USD/Month |
| F and I penetration | F and I base penetration + F and I maximum penetration uplift * (1 - EXP(-F and I programme spend / F and I spend scale)) | Dmnl |
| F and I income | (new sales + used sales) * F and I penetration * F and I gross per contract * (1 - chargeback rate) | USD/Month |
| service gross | ro done * gross per repair order | USD/Month |
| parts gross | ro done * parts gross per repair order | USD/Month |
| total gross | new gross + used gross + lease remarketing gain + F and I income + service gross + parts gross | USD/Month |
| commissions | commission rate * (new gross + used gross + F and I income) | USD/Month |
| technician payroll | Technicians * technician cost monthly | USD/Month |
| wholesale loss | wholesale exits * wholesale loss per vehicle | USD/Month |
| floorplan rate effective | floorplan rate monthly + rate shock size / months per year * shock active | 1/Month |
| floorplan interest | Floorplan Debt * floorplan rate effective | USD/Month |
| net profit | total gross - commissions - marketing spend - F and I programme spend - technician payroll - wholesale loss - fixed overhead - floorplan interest | USD/Month |
| net cash flow | net profit - (1 - advance rate) * (deliveries * new vehicle unit cost + used acquisitions * used vehicle unit cost - inventory cost released) | USD/Month |
| Cash | initial cash + Cash Received - Cash Paid Out | USD |
| Cumulative Net Profit | Cumulative Profit Earned - Cumulative Loss Incurred | USD |
| Cumulative Discounted Cash Flow | Cumulative Discounted Cash Received - Cumulative Discounted Cash Paid | USD |
| discount factor | EXP(-discount rate monthly * Time) | Dmnl |
| discounted net cash flow | net cash flow * discount factor | USD/Month |
| absorption rate | (service gross + parts gross - technician payroll) / fixed overhead | Dmnl |
| floorplan rate monthly | floorplan rate / months per year | 1/Month |
| discount rate monthly | discount rate / months per year | 1/Month |
| shopping rate monthly | shopping rate / months per year | 1/Month |
| base defection rate monthly | base defection rate / months per year | 1/Month |
| attrition rate monthly | attrition rate / months per year | 1/Month |
| wholesale exit rate monthly | wholesale exit rate / months per year | 1/Month |
| visits per customer monthly | visits per customer / months per year | RO/(Household*Month) |
| technician cost monthly | technician cost / months per year | USD/(Technician*Month) |

## Parameters (constants; each gets base, range, distribution, source and confidence tag at gate 5)

| Sector | Constants (unit) |
|---|---|
| Time and unit conversion | months per year (Month/Year); days per month (Day/Month); vehicles per household purchase (Vehicle/Household); number of lease stages (Dmnl); simulation horizon (Month); minimum sellout time (Month) |
| Demand and prospects | shopping rate (1/Year); new share of shoppers (Dmnl); market entry rate (Household/Month); maximum marketing starts (Household/Month); marketing spend scale (USD/Month); marketing spend (USD/Month) |
| New vehicles | availability constant new (Vehicle); target new days supply (Day); new inventory adjustment time (Month); order lead time (Month); manufacturer allocation (Vehicle/Month); allocation response strength (Dmnl); reference new sales (Household/Month); allocation memory (Month) |
| Used vehicles | availability constant used (Vehicle); discount demand sensitivity (Dmnl); discount sensitivity (Dmnl); maximum price discount (Dmnl); target used days supply (Day); used inventory adjustment time (Month); used sales memory (Month); reference used sales (Household/Month); reconditioning time (Month); wholesale exit rate (1/Year); minimum used sales rate (Vehicle/Month); trade in share (Dmnl); off lease return share (Dmnl) |
| Customer base and leases | lease share (Dmnl); lease term (Month); ownership period (Month); loyalty floor (Dmnl); loyalty ceiling (Dmnl); loyalty half saturation (Dmnl); minimum owner base (Household) |
| Service and parts | service capture share (Dmnl); base defection rate (1/Year); visits per customer (RO/(Household*Year)); repairs per technician (RO/(Technician*Month)); retention loss when overloaded (Dmnl); technician target (Technician); hire time (Month); attrition rate (1/Year) |
| F and I | F and I base penetration (Dmnl); F and I maximum penetration uplift (Dmnl); F and I spend scale (USD/Month); F and I programme spend (USD/Month); F and I gross per contract (USD/Household); chargeback rate (Dmnl) |
| Profit, cost and financing | new gross per vehicle (USD/Vehicle); used gross per vehicle (USD/Vehicle); used retail price (USD/Vehicle); lease remarketing loss per vehicle (USD/Vehicle); gross per repair order (USD/RO); parts gross per repair order (USD/RO); technician cost (USD/(Technician*Year)); fixed overhead (USD/Month); commission rate (Dmnl); wholesale loss per vehicle (USD/Vehicle); new vehicle unit cost (USD/Vehicle); used vehicle unit cost (USD/Vehicle); advance rate (Dmnl); floorplan rate (1/Year) |
| Scenario levers, shocks and valuation | margin shock size (Dmnl); rate shock size (1/Year); demand shock size (Dmnl); shock start month (Month); shock duration (Month); discount rate (1/Year) |

## Unit checks by hand (T1 repeats them on the PySD translation)
- `target used inventory` = (Household/Month x Vehicle/Household x Day) / (Day/Month) = Vehicle. Days-supply is
  `Vehicle / (Vehicle/Month) x Day/Month` = Day.
- `trailing change` = (Household/Month - Household/Month) / Month, so `Trailing New Sales` (Household/Month) is the
  integral of Household/Month/Month.
- `visits per customer monthly` = RO/(Household*Year) / (Month/Year) = RO/(Household*Month), so `ro demand` =
  Household x RO/(Household*Month) = RO/Month, the unit of `capacity` = Technician x RO/(Technician*Month).
- `floorplan rate effective` = 1/Month + (1/Year) / (Month/Year) = 1/Month; `discount factor` = EXP(-1/Month x Month) is dimensionless.
- `inventory cost released` = Household/Month x Vehicle/Household x USD/Vehicle = USD/Month.

## How the lenses act on this structure (equal-sized lever changes unless you set real programmes, gate 8)
| Lens | Levers and shocks (all constants or time-driven, no new links) |
|---|---|
| A. Allocation | `target used days supply` (used inventory depth), `technician target` (service capacity), `F and I programme spend`, `marketing spend` |
| B. Resilience | `margin shock size`, `rate shock size`, `demand shock size`, within one window set by `shock start month` and `shock duration`; one at a time and combined |
| C. Strategy | mix levers: `new share of shoppers` (used-heavy), `lease share` (lease-heavy), `technician target` and `service capture share` (fixed-ops-heavy) |
| D. Valuation | `discount rate`; reads `discounted net cash flow`, no lever |

Lever costs are in the model: technician payroll, floorplan interest on a deeper used inventory, F&I programme spend,
marketing spend. So each scenario pays for what it buys, and cumulative net profit compares them fairly.

## Conservation (T6 groups, plus identities checked by a project script `checks.py`)
- **Households (T6):** Households Outside Market + Prospects + Owners + Lessees Early + Lessees Mid + Lessees Late +
  Households Elsewhere = constant. Every flow moves a household between two of these stocks: market entries and
  marketing starts leave the outside pool; sales move prospects to owners or lessees; replacement and lease end
  return a household to Prospects (`repeat to store`) or to Households Elsewhere (`leakage`).
- **New vehicles (T6):** Manufacturer Supply Outside + New Vehicles On Order + New Inventory + New Vehicles Sold = constant.
- **Used vehicles (T6):** Used Vehicle Supply Outside + Reconditioning Pipeline + Used Frontline Inventory + Used
  Vehicles Sold On = constant (wholesale exits count as sold on).
- **Equity identity (script, not T6, because it needs a signed sum):** Cash + Inventory at Cost - Floorplan Debt - Cumulative Net Profit = its initial value, every step. It holds by construction: net cash flow = net profit - (1 - advance rate) x (purchases at cost - cost released).
- **P&L identity (script):** net profit = total gross - commissions - marketing spend - F&I programme spend - technician payroll - wholesale loss - fixed overhead - floorplan interest, every step (relative error < 1e-6).
- **Not conserved, by design:** Trailing New Sales (information), Trailing Used Sales (information), Service Customers (a subset of owners and lessees
  with its own entry and defection), Technicians (a resource), Cumulative Net Profit and Cumulative Discounted Cash Flow (accumulators).

## Delays (explicit stocks, all first order except the lease term, a three-stage chain)
Lease term (Lessees Early/Mid/Late, third-order, mean = `lease term`), ownership period (Owners), reconditioning time
(Reconditioning Pipeline), order lead time (New Vehicles On Order), allocation memory (Trailing New Sales), used sales memory (Trailing Used Sales), hiring and
attrition (Technicians), service tenure (Service Customers). Longest in the expected ranges: replacement cycle
36-72 months, so the 180-month horizon is >= 3x (gate 1). Shortest: reconditioning time, a fraction of a month. Gate 5
sets the time step from it (dt <= one quarter of it, T4).

## Simplifications to carry into "Model limits"
- Shoppers that find no stock wait in Prospects rather than leaving; only buying removes a prospect. Prospects
  who would buy elsewhere are never created.
- Service customers have their own defection rate; they do not drop when the owner they belong to is replaced.
- Used-vehicle demand rises with discount through one linear sensitivity; the sensitivity range is `estimated`.
- `new orders` is capped by `manufacturer allocation` (a hard cap, inactive in the base run).

## Limit case for T5 (gate 1) in this structure
`lease share` = 0, `F and I base penetration` = 0 with uplift 0, `service capture share` = 0, `allocation response
strength` = 0, `retention loss when overloaded` = 0, no shocks, with `used price discount` links neutral
(`discount sensitivity` = 0, `discount demand sensitivity` = 0) and flat demand: used inventory then follows the
stock-management archetype (`library/archetypes.md` §6). The analytic reference and tolerances are fixed at gate 5.

## Policy comparison (as in the SaaS worked example)
`engine/validate.py` measures every policy's gain per sample against the **first** policy in `[[policies]]`, and
takes the Monte Carlo bands from that scenario. **"Baseline store, no lever change" is listed first.** The base
parameter set keeps leases, F&I and service all on (gate 3 condition 2), so base, dt-halving, extreme and T8 runs
exercise every loop. Funded scenarios' bands come from separate runs at gate 8 with the same samples and seed.
