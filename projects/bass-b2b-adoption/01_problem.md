# Gate 1: Problem articulation

**Question (as given):** "How fast will adoption of a new B2B software product grow, and what limits it?"

**Decision the model informs.** The question names no decision. Under `/sd-model` this gate stops and asks. For this test run (plan approved to run straight through) the decision is **assumed** and must be confirmed by the user:

> Which growth lever to fund first over the first 5 years (marketing reach, referral/word of mouth, sales win rate, sales cycle length, customer success/churn), and what range of customer count and market share to plan for at month 60.

**Product context (assumed):** mid-market B2B SaaS, sold through a sales-led evaluation (trial, proof of concept, procurement), closed target market of identifiable firms.

## Key variables
| Variable | Unit | Role |
|---|---|---|
| Customers | Firm | main outcome (logos) |
| Customer share = Customers / total market | Dmnl | outcome independent of market size |
| Firms in Evaluation | Firm | sales pipeline |
| Evaluation starts | Firm/Month | demand generation (Bass adoption flow) |
| Deals won, churn | Firm/Month | conversion and attrition |

## Time horizon
180 months (15 years); decision horizon 60 months. Rule: horizon >= 3x the longest delay (`library/modeling_checklist.md` item 1); longest delay in the ranges is the 36-month cool-off, so >= 108 months. 15 years is chosen so the saturation limit is visible: at base parameters customer share is still rising at month 120.

## Reference modes
- **Historical:** none. The product is new and the repo holds no adoption data; none is invented. Behavior reproduction (T5) is therefore against the analytic Bass solution in a limit case plus the expected qualitative modes below, not against history.
- **Expected (stylized), stated before validation:**
  1. Customers: S-shaped growth (slow start from design partners, acceleration through word of mouth, deceleration), approaching a plateau **below** the total market because churned and lost firms cycle out.
  2. Customer share: same S shape.
  3. Evaluation starts: rise as word of mouth builds, then flatten or decline as the potential pool depletes.
  4. Limit case (no churn, every deal won, near-zero sales cycle): customers + evaluations follow the closed-form Bass curve, peak adoption at t* = ln(q/p)/(p+q) (`library/archetypes.md` section 4, `[verified]`).
