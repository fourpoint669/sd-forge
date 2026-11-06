# Gate 5: Assumptions register

Confidence tags: **verified** = checked in this repo; **reported** = from a cited source, not checked against the primary document; **estimated** = judgement or derived. Every parameter has a range and a distribution; Monte Carlo (T7) samples all eight.

## Parameters

| Parameter | Base | Range (distribution) | Unit | Source | Confidence |
|---|---|---|---|---|---|
| marketing reach rate (p for entering evaluation) | 0.14 | 0.05-0.25 (triangular) | 1/Year | Bass innovation coefficient p ~ 0.03/yr: mean of the Sultan, Farley and Lehmann (1990) meta-analysis of 213 diffusion applications, mostly consumer durables (reported via secondary sources, see sources.md); divided by base win rate 0.21 to express it as entry into evaluation. Range from p 0.01-0.05 / win rate. | estimated (derived from reported) |
| word of mouth rate (q for entering evaluation) | 1.8 | 1.0-2.9 (triangular) | 1/Year | Bass imitation coefficient q ~ 0.38/yr (same meta-analysis; common range 0.2-0.4, widened to 0.2-0.6) divided by 0.21. B2B transfer of consumer-durable coefficients is itself an assumption. | estimated (derived from reported) |
| sales cycle time | 6 | 3-9 (triangular) | Month | Secondary benchmarks: Ebsta-based medians ~84 days SMB, ~170 days mid-market; KeyBanc median ~6 months (as quoted by vendor blogs, not read in the original). | reported (secondary) |
| win rate | 0.21 | 0.15-0.30 (triangular) | Dmnl | Gong benchmark: median ~21% on qualified B2B SaaS opportunities (as quoted secondhand). | reported (secondary) |
| annual logo churn rate | 0.08 | 0.05-0.20 (triangular) | 1/Year | Secondary benchmarks for mid-market: 5-8% (ChartMogul figures as quoted), 7-12% (MeltingSpot); one study reports ~33%. Sources disagree; range kept wide, upper end capped at 20%. | reported (secondary, conflicting) |
| cool off time | 18 | 12-36 (triangular) | Month | Annual budget/contract cycles; no source found. | estimated |
| total market | 5,000 | 3,000-8,000 (triangular) | Firm | Illustrative target-market count. **Replace with your own market sizing.** | estimated |
| initial customers | 10 | 5-25 (triangular) | Firm | Design partners at launch. | estimated |
| months per year | 12 | none | Month/Year | Definition. | verified |
| initial firms in evaluation, initial cooling off firms | 0 | none | Firm | Launch state. | estimated |

## Structural assumptions (not parameters)

| # | Assumption | Effect if wrong |
|---|---|---|
| S1 | Firms are homogeneous: one win rate, one churn rate, one sales cycle for all. | Segments with different economics (SMB vs enterprise) blur; bands understate segment spread. |
| S2 | Lost and churned firms return after the cool-off and behave like fresh prospects (same win rate). | From ~month 80 the dominant loop is lost-deal recycling (R3, see validation report T8). If returning firms convert worse, long-run growth is overstated. |
| S3 | Word of mouth comes from customers only, in proportion to customer share (Bass imitation). | Referral programmes that work through evaluators or communities are not represented. |
| S4 | No sales or onboarding capacity limit. | Fast-growth samples are optimistic; capacity would cap deals won. |
| S5 | Parameters are constant for 15 years (no product improvement, no competitor response, no price changes). | Long-horizon bands are conditional on a static world. |
| S6 | Closed market of fixed size. | Market growth or new segments would raise the ceiling. |
| S7 | Continuous flows of firms (fractional firms allowed). | Negligible above ~50 firms; early months with < 20 customers are approximate. |
| S8 | Bass p and q estimated mostly on consumer durables transfer to B2B software. | p, q ranges may be off; they are the most influential uncertain inputs for months 12-60 (validation report, Spearman table). |
