# Sources and licence

## Building blocks taken from this repo
| Item | Path | MANIFEST commercial_use | Use |
|---|---|---|---|
| Bass diffusion archetype (own-words notes) | `library/archetypes.md` section 4 | n/a (repo's own notes) | equations, analytic peak time |
| Validation tests and tolerances | `library/validation_tests.md` | n/a | thresholds |
| Unit conventions | `library/units.md` | n/a | unit rules |

No file under `raw/` was copied, adapted or translated into this model: the `.mdl` is original. **Share-alike content reused: none** (no share-alike source is in the repository).

## Pointer-only references (studied for numbers or method, nothing copied)
| Reference | MANIFEST row | Used for |
|---|---|---|
| Bass (1969), A new product growth model for consumer durables, Management Science 15(5) | `pointer:bass-1969-new-product-growth` (commercial_use=no) | model structure (as already summarised in `library/archetypes.md`) |
| Sultan, Farley and Lehmann (1990), A meta-analysis of applications of diffusion models, Journal of Marketing Research 27(1):70-77 | none (copyrighted paper, not added to MANIFEST) | p ~ 0.03, q ~ 0.38; read only through secondary summaries ([Columbia Business School abstract](https://business.columbia.edu/faculty/research/meta-analysis-applications-diffusion-models), [Wikipedia: Bass diffusion model](https://en.wikipedia.org/wiki/Bass_diffusion_model)) |
| Schoenberg, Davidsen and Eberlein (2020), Understanding model behavior using the Loops that Matter method, System Dynamics Review | none (copyrighted) | loop-dominance method reimplemented in `engine/loop_detector.py` from its published definition |
| B2B SaaS sales and churn benchmarks (vendor blogs quoting Gong, Ebsta, KeyBanc, ChartMogul) | none (web pages) | sales cycle, win rate, churn ranges: [The Digital Bloom pipeline benchmarks](https://thedigitalbloom.com/learn/pipeline-performance-benchmarks-2025/), [MeltingSpot churn benchmark](https://meltingspot.io/en/blog/saas-b2b-churn-rate-benchmark), [StealthAgents churn statistics](https://stealthagents.com/research/saas-churn-rate-statistics-2026), [Visionary Marketing SaaS cohort study](https://visionary-marketing.co.uk/blog/saas-churn-benchmarks-2026) |

None of the secondary figures was checked against its primary report; every parameter derived from them is tagged `reported (secondary)` or `estimated` in `assumptions_register.md`.
