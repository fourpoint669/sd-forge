# Gate 2: Model boundary

| Variable | Status | Justification |
|---|---|---|
| Potential customers, firms in evaluation, customers, cooling-off firms | Endogenous (stocks) | The adoption process itself; every firm in the market is in exactly one of them. |
| Evaluation starts (marketing-driven and word-of-mouth), deals won/lost, churn, re-entry | Endogenous (flows) | Driven by the stocks; carry all feedback loops. |
| Customer share | Endogenous | Drives word of mouth (imitation term of Bass). |
| Total market (firms) | Exogenous, constant | Market sizing is an input; the model asks how fast it is penetrated, not how big it is. Range 3,000-8,000 covers sizing error. |
| Marketing reach rate, word-of-mouth rate | Exogenous (policy levers) | Set by spend and referral programmes; no budget feedback modelled. |
| Win rate, sales cycle time | Exogenous (policy levers) | Set by product fit and sales execution; held constant over the run. |
| Annual logo churn rate | Exogenous (policy lever) | Set by product value and customer success; held constant. |
| Cool-off time | Exogenous | Budget/contract cycle before a lost or churned firm re-evaluates. |
| Sales capacity (reps, onboarding) | **Excluded** | Would add a capacity constraint (growth and underinvestment, `library/archetypes.md` section 9/10). Excluded to keep the test case to the Bass + saturation question; listed as a model limit. |
| Competitors, price, product quality over time | **Excluded** | No competitor data; would make win rate and churn endogenous. Model limit. |
| Revenue, expansion, seats, pricing tiers | **Excluded** | The question is about adoption (logos), not revenue. |
| Market growth (new firms entering the market) | **Excluded** | Closed market; acceptable over 15 years only if the firm count is stable. |
| Network effects inside a customer, product-led self-serve funnel | **Excluded** | Sales-led product assumed. |

Boundary test (T2 in `library/validation_tests.md`): the excluded items most likely to feed back on adoption within 5 years are sales capacity and competitive response. Both are named in the summary's model limits.
