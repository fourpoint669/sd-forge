# Unit conventions

Own-words conventions for models intended to run in PySD/Vensim. `[unverified]` = convention from practice, not checked by a test here; `[verified: ...]` = checked.

1. Every variable carries a unit; time unit is declared once (e.g. Month) and every rate is `<stock unit>/<time unit>`. [unverified]
2. A stock's unit times 1/time equals the unit of each flow into/out of it. [unverified]
3. Use `Dmnl` (dimensionless) for ratios, fractions, multipliers, effects. `1/Month` for fractional rates. [unverified]
4. Convert units by an explicit constant variable (e.g. `Days per Month`), never an unlabeled number. [unverified]
5. Time constants (delay times, smoothing times, adjustment times) are in time units; never use a rate where a time constant is meant. [unverified]
6. Currency: `$` or `USD`; per-capita values as `$/Person`. Keep price index separate from price level. [unverified]
7. People/items counted in whole units but modeled as continuous: say so in the model notes. [unverified]
8. TIME STEP should be at most 1/4 of the shortest time constant, and a power of 2 so that it is exact in binary (both are published guidance: Sterman (2000) appendix A, "Guidelines for Numerical Integration", p. 910; test T4 checks integration error but neither of these two rules). [verified: engine/verify_archetypes.py shows Euler error halving with dt]
9. PySD stores units as strings and does not perform unit arithmetic checking itself; do the check with an external script or Vensim's Units Check. [unverified]
