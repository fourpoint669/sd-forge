# Sources and licence

## Building blocks taken from this repo
| Item | Path | MANIFEST commercial_use | Use |
|---|---|---|---|
| Customer engine structure (Bass demand, sales pipeline, churn, cool-off) | `projects/bass-b2b-adoption/model/bass_b2b_adoption.mdl` | n/a (this repo's own original model) | structure and base parameters reused; regression-checked bit for bit by `checks.py` |
| Bass, goal-seeking and limits-to-growth archetypes (own-words notes) | `library/archetypes.md` | n/a (repo's own notes) | loop mapping, analytic Bass reference |
| Validation tests and tolerances | `library/validation_tests.md` | n/a | thresholds |
| Unit conventions, modeling checklist | `library/units.md`, `library/modeling_checklist.md` | n/a | unit rules, process |

No file under `raw/` was copied, adapted or translated into this model; the `.mdl` is original. **Share-alike content
reused: none** (no share-alike source is in the repository).

## Pointer-only references (studied for numbers or method, nothing copied)
| Reference | MANIFEST row | Used for |
|---|---|---|
| Bass (1969), A new product growth model for consumer durables | `pointer:bass-1969-new-product-growth` (commercial_use=no) | model structure, via `library/archetypes.md` |
| Sultan, Farley and Lehmann (1990), meta-analysis of diffusion models | none (copyrighted) | Bass p and q, read through secondary summaries (see `projects/bass-b2b-adoption/sources.md`) |
| Schoenberg, Davidsen and Eberlein (2020), Loops that Matter | none (copyrighted) | loop dominance method, reimplemented in `engine/loop_detector.py` |

## Benchmark sources for parameters (web pages, read through search results; none checked against the primary report)
| Parameter(s) | Source |
|---|---|
| net expansion, GRR/NRR consistency check, expansion lift A | [SaaS Capital retention benchmarks](https://www.saas-capital.com/research/saas-retention-benchmarks-for-private-b2b-companies/), [2025 report PDF](https://www.saas-capital.com/wp-content/uploads/2025/09/RB32WS1-2025-B2B-SaaS-Retention-Benchmarks.pdf), [KeyBanc 2024 as quoted by Stackmatix](https://www.stackmatix.com/blog/net-revenue-retention-benchmarks), [Directive retention bands](https://directiveconsulting.com/blog/blog-b2b-saas-retention-benchmarks/) |
| new customer ACV | [sales-mind KPI benchmarks](https://sales-mind.ai/blog/post/kpi-benchmarks-saas-sales-teams-2025) |
| CS cost per covered firm | [StealthAgents CSM cost](https://stealthagents.com/research/cost-of-hiring-a-customer-success-manager-2026), [Customer Success Collective salary report](https://customersuccesscollective.com/customer-success-salary-report-2024), [Founderpath CSM salary](https://founderpath.com/salary-benchmarks/saas/customer-success-manager), [Fullview accounts per CSM](https://fullview.io/blog/how-many-accounts-customer-success), [Tunguz ARR per CSM](https://www.tomtunguz.com/how-much-arr-can-a-csm-manage/index.md) |
| maximum churn reduction | [Gainsight](https://www.gainsight.com/blog/managing-churn-in-saas-business-with-a-focus-on-customer-success/), [Refiner](https://refiner.io/blog/wp-json/wp/v2/posts/2128), [Voxbooster](https://www.voxbooster.com/de/blog/saas-churn-statistics-2026) |
| maximum win rate uplift, win spend scale | [Highspot on CSO Insights](https://www.highspot.com/blog/cso-insights-finds-mature-sales-enablement-delivers-increasing-business-impact), [Highspot enablement statistics](https://highspot.com/blog/25-sales-enablement-stats-to-prove-your-revenue-impact) |
| sales cycle, base win rate, base churn | as in `projects/bass-b2b-adoption/sources.md` |

Every parameter derived from these is tagged `reported (secondary)` or `estimated` in `assumptions_register.md`.
