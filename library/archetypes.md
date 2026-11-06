# Archetype catalog

Own-words notes. Tags: `[verified: engine/verify_archetypes.py]` = reproduced numerically by that script (toy parameters, qualitative/analytic behavior only); `[unverified]` = from memory or the cited literature, not checked here. Loop polarity: **R** reinforcing, **B** balancing. Notation: S stock, g fractional growth rate, K carrying capacity, tau time constant.

The fundamental modes in 1-3 and their interactions are the published set (Sterman (2000) §4.1-4.3); the named archetypes in 7 and 10 are Senge's (1990); Bass and SIR have their own primary papers (see `library/notes/bass-and-sir-papers.md`). Pointers: `library/notes/`. Only the lines tagged `[verified: ...]` have been reproduced by a script here, whatever their source says.

## 1. Exponential growth (R)
- Structure: S -> inflow = g*S -> S. One R loop.
- Equations: dS/dt = g S; S(t) = S0 e^{gt}. [verified]
- Behavior: exponential growth; doubling time ln2/g. [verified]
- Related models: raw/test-models (simple stock-flow tests), PySD tutorials.

## 2. Goal seeking (B)
- Structure: gap = goal - S; inflow = gap/tau.
- Equations: dS/dt = (G - S)/tau; S(t) = G - (G - S0) e^{-t/tau}. [verified]
- Behavior: asymptotic approach, no overshoot; 63% of gap closed in one tau. [verified]
- Models: teacup (Newtonian cooling) in raw/test-models/tests/teacup.

## 3. Limits to growth / S-shaped growth (R + B)
- Structure: R growth loop plus B loop that strengthens as S nears K.
- Equations: dS/dt = g S (1 - S/K). [verified]
- Behavior: S-curve; max growth rate at S = K/2; converges to K. [verified]
- Variant with delay in the B loop: overshoot and oscillation (see 6). Variant where K is itself eroded by S: overshoot and collapse (see 8). Both variants are described at Sterman (2000) §4.2.2-4.2.3, pp. 121-126. [unverified here]

## 4. Bass diffusion (R + B, adoption)
- Structure: Potential adopters P -> adoption rate -> Adopters A. Adoption rate = innovation p*P + imitation q*A*P/N.
- Equations: dA/dt = (p + q A/N)(N - A). [verified]
- Behavior: S-curve for A; adoption rate is bell-shaped; peak at t* = ln(q/p)/(p+q) with A* = N(q-p)/(2q) (needs q>p). [verified]
- Typical parameters in the literature: p ~ 0.01-0.03, q ~ 0.3-0.5. [unverified]
- Commercial uses: new product launch, subscriber adoption; add repeat purchase/churn to get steady state.
- Validated model with a B2B sales pipeline, churn and re-entry: `projects/bass-b2b-adoption/` (11 loops, Monte Carlo bands; see its `summary.md`). [verified: engine/validate.py]

## 5. SIR epidemic (R + B)
- Structure: S -> infection -> I -> recovery -> R. Infection = beta S I / N.
- Equations: dS=-beta S I/N; dI=beta S I/N - gamma I; dR=gamma I. R0 = beta/gamma. [verified for conservation, peak and final size]
- Behavior: if R0>1, I rises then falls; peak when S = N/R0; S+I+R constant; final size z solves z = 1 - e^{-R0 z}. [verified]
- Business analogues: viral spread, word of mouth, rumor, churn contagion.

## 6. Stock management with delay (B with delay)
- Structure: stock S, goal G, correction = (G - perceived S)/tau_a, perception lags the stock by tau_d.
- Equations: dS/dt = (G - P)/tau_a; dP/dt = (S - P)/tau_d. [verified]
- Behavior: overshoot above goal then oscillation damped to goal when tau_d is comparable to tau_a. [verified: overshoot ~68% with tau_a=2, tau_d=4]
- Extended into the supply-chain / beer game structure: ordering amplification up the chain (bullwhip). [unverified here; see raw/bptk-py/.../beergame]
- **Not modelled here:** the full stock management structure adds a *supply line* of units already ordered but not yet arrived, and neglecting it is what turns this B loop into sustained oscillation (Sterman (2000) §17.3 p. 675, §17.4.1-17.4.2 pp. 684-695). The toy check below has no supply line, so it shows overshoot, not the amplification and phase lag of a real supply chain. [unverified here]
- Inventory/workforce: inventory coverage, desired production = demand + adjustment for inventory, workforce adjustment delay.

## 7. Shifting the burden (B + B + R)
- Structure: a problem symptom triggers a fast symptomatic fix (B1) and a slow fundamental solution (B2). The fix has a side effect that erodes capability for the fundamental solution (R).
- Toy equations used for the check: gap' = pressure - fix - fund*cap; cap' = recover*(1 - cap) - erosion*fix*cap. [verified: capability ends well below its starting value and the gap stays higher than without erosion]
- Behavior: improvement in the symptom, growing dependence on the fix, long-term decline of fundamental capability. [verified for toy model; general archetype description from Senge [unverified]]
- Commercial examples: discounting to hit quarterly targets while brand/pricing power erodes. [unverified]

## 8. Resource depletion (overshoot and collapse)
- Structure: capital K extracts from a finite stock R; output reinvested in K; K depreciates; extraction slows as R gets scarce.
- Toy equations: R' = -a K R/(R + h); K' = reinvest*extraction - dep*K. [verified: extraction rises, peaks (t~220 in the toy), then falls to near zero]
- Behavior: growth, peak, decline (Hubbert-like). World3's nonrenewable resource sector uses the same logic with more detail. [unverified for World3 details]

## 9. Market growth / capacity (R + B with delay)
- Structure: demand growth -> revenue -> capacity investment (delayed) -> service quality -> demand. Can produce growth-and-underinvestment. [unverified]
- Use raw/bptk-py customer_acquisition and competitive_pricing models as concrete starting points.

## 10. Other named archetypes (not modeled here) [unverified]
Fixes that fail, tragedy of the commons, success to the successful, escalation, growth and underinvestment, accidental adversaries, eroding goals. Descriptions in Senge (1990), pointer in MANIFEST.csv.
