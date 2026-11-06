# Gate 4: Stock-flow structure

Time unit: Month. All stocks in Firm; all flows in Firm/Month (`library/units.md` rules 1-2). Fractional rates given per year in the sources are converted with the named constant `months per year` = 12 Month/Year (rule 4), never a bare 12.

| Stock (Firm) | Inflows (Firm/Month) | Outflows (Firm/Month) | Initial value |
|---|---|---|---|
| Potential Customers P | re entry | evaluation starts | total market - initial customers |
| Firms in Evaluation E | evaluation starts | deals won, deals lost | 0 |
| Customers C | deals won | churn | initial customers |
| Cooling Off Firms F | deals lost, churn | re entry | 0 |

| Flow / auxiliary | Equation | Unit |
|---|---|---|
| evaluation starts | marketing driven starts + word of mouth starts | Firm/Month |
| marketing driven starts | marketing reach rate monthly x P | Firm/Month |
| word of mouth starts | word of mouth rate monthly x P x customer share | Firm/Month |
| customer share | C / total market | Dmnl |
| deal closings | E / sales cycle time | Firm/Month |
| deals won / deals lost | deal closings x win rate / x (1 - win rate) | Firm/Month |
| churn | C x churn rate monthly | Firm/Month |
| re entry | F / cool off time | Firm/Month |
| marketing reach rate monthly, word of mouth rate monthly, churn rate monthly | annual rate / months per year | 1/Month |

## Conservation
Every flow leaves one stock and enters another, so P + E + C + F = total market at all times (closed market). Checked by T6: maximum relative drift 3.0e-15 across the base run, the fastest-corner run and all 6,000 Monte Carlo runs (limit 1e-6). Dimensional consistency of all 27 equations, including flow x time = stock for each stock: T1, 0 problems.

## Delays
Both delays are first-order material delays written as explicit stocks (not SMOOTH/DELAY functions), so the loop detector can score every loop: sales cycle (E drains at E / sales cycle time) and cool-off (F drains at F / cool off time).
