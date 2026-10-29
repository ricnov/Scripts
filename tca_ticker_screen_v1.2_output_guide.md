# `tca_ticker_screen.py` v1.2 — Output guide

## Purpose and scope of this guide

`tca_ticker_screen.py` is a ticker-level transaction cost screen for the ADR and common-stock order flow of the SMA platform. For every ticker traded over the analysis window the script:

1. measures the cost of taking liquidity on each order (the **liquidity tax**, defined in §2.2: effective half-spread plus an impact leg);
2. compares that cost with the cost observed on comparable name-days, where "comparable" means the same band of platform-level daily participation rate and the same volatility tercile, measured on other tickers only (the **liquidity excess**, §2.5);
3. fits a per-ticker **cost curve** of the daily liquidity tax against the square root of the platform's daily participation rate, shrunk towards the curve of the ticker's peer group (§2.7);
4. classifies the ticker as *expensive to trade on a typical day* ("wide"), *expensive only at the participation rate the platform runs* ("at size"), *expensive on implementation shortfall but not on liquidity* ("drift name"), or not expensive (§2.8);
5. tracks the classification over time: persistence by calendar month, a recent-period lens for names whose cost has changed, and, in `--daily` mode, a run-by-run history (§2.9–2.11).

The script writes an HTML/Markdown/Excel report, up to fourteen CSV tables (`markouts` requires the fills store, `changes` a baseline, `recent_movers` and `recent_drift` an active recent lens), up to seven PNG charts and a JSON summary. This guide describes how each quantity is computed, what a high or low value means in execution terms, and which outputs the execution desk should review on each run as opposed to the outputs that are inputs for portfolio construction and the transaction-cost model. §1 lists the files; §2 defines every quantity; §3 covers the tables; §4 covers the charts; §5 gives the reading order for the desk; §6 records labelling defects found in the plotting code.

### Conventions

- All costs are in basis points (bp) of the relevant reference price, signed so that a **positive value is a cost** to the platform and a negative value is a saving. `side` is +1 for a buy (`BUY_SELL_CD` B or CS) and −1 for a sell.
- Unless a column name says `median` or `day-mean`, every aggregate is weighted by filled notional (dollar-weighted; "$-w" in column names).
- "Name" and "ticker" are synonyms. The "slice" is the set of orders selected for the run. The "window" is the run's date range. "The platform" is the aggregate of all SMA accounts; an "order" is one account-level order as reconciled in the TCA store.
- Script defaults (quoted throughout): `--liq-bps 5`, `--excess-bps 5`, `--spread-bps 8`, `--impact-bps 3`, `--tax-clip 200`, `--min-orders 20`, `--min-days 5`, `--min-notional 1e6`, `--adv-bands 0.1,0.5,2,5,15,50`, `--worked-minutes 15`, `--markout-min 5`, `--markout-cov 20`, `--se-floor 0.1`, `--recent-days 20`, `--recent-min-orders 8`, `--top 50`. The values in force for a given run are printed in the report's "Scope and method" section and stored in `slice.json → thresholds`.

---

## 1. Files produced by a run

```
<out>/                                    default: reports/ticker_screen_<types>_<start>_<end>/
  report.html, report.md, report.xlsx     the report (see below)
  tables/*.csv                            the tables in full; the report shows only the top --top rows of the long ones
  charts/*.png                            the charts (up to seven)
  slice.json                              run parameters, slice statistics, every list as an array of tickers
```

In `--daily` mode the output folder is `reports/ticker_screen_<types>/<end date>/`, the previous dated folder is used as the baseline, and three further objects are maintained in the root folder: `history.csv` (one row per flagged name per run date), `runs.csv` (one row per run) and `latest/` (a copy of the most recent run). `--keep N` deletes all but the last N dated folders.

**Structure of the report.** A strip of KPI tiles (window; slice composition; number of names screened; slice implementation shortfall and liquidity tax; watch-list size with the wide and at-size counts; liquidity-excess dollars of the watch list; number of portfolio-side priority names; number and dollars of drift names; cost-model R²; movers over the recent period; entries and exits since the previous list), an executive summary paragraph, the numbered findings and the recommended actions, and then six sections: *Scope and method*, *Watch list — expensive to trade*, *Cost curves — the per-ticker input for the TC model*, *Expensive, not for liquidity reasons*, *Recent movers*, *Every name*. Each section contains its tables and a "reading" paragraph that restates the table's main figures in sentences; some sections add a numbered finding and recommendations. The reading paragraphs are generated from the tables, so they are a summary of the data rather than an independent judgement.

---

## 2. Definitions

### 2.1 Population

**Orders.** The run selects the orders of the window with the requested security types (default: ADR and Common Stock; `--sec-type` is repeatable and accepts the aliases defined in `tca_report.py`). Of those, it keeps the orders that `tca_core.prepare` marks as reconciled (`RECON` true: the arrival price, the fills and the closing price form a consistent chain) and that have a positive filled notional. The window defaults to year-to-date up to the last trade date in the store; when year-to-date covers fewer than 90 calendar days the window is the trailing 180 days; `--start`, `--end` and `--window-days` override this.

**Thin names.** A ticker with fewer than 20 orders, fewer than 5 distinct trading days or less than $1M of filled notional over the window is marked `thin`. Thin names appear in `tickers.csv` with every column computed, but no flag is ever set on them and they never enter the watch list, the drift table or the mover lists. The KPI tile "Names screened" is the number of non-thin names.

### 2.2 Cost measures per order

| quantity | definition | sign and reading |
|---|---|---|
| **Implementation shortfall** (`IS_BPS`) | side × (average execution price − arrival price) / arrival price × 10⁴, where the arrival price is the reference price at order arrival in the TCA store | Positive: the order executed at a worse price than the arrival price. It contains both the cost of taking liquidity and the price movement during the life of the order. |
| **Winsorised IS** (`IS_W`) | `IS_BPS` clipped to ±300 bp per order | Used only in the slice-level tables, to limit the influence of individual outliers on the type averages. |
| **Effective half-spread** (`EFF_HS`) | side × (fill price − midpoint at the fill) / midpoint × 10⁴, aggregated over the order's fills (`EFF_HALF_SPREAD_BPS`). The report's method section states whether the midpoint is taken from the quotes stamped on the fill records ("fill quotes") or from the arrival quotes; the choice is stored as `spread_lens` in `slice.json`. Where the field is missing, the quoted half-spread is used in its place. | Positive: the fill paid part or all of the spread (liquidity-taking execution). Zero: fills at the midpoint. Negative: fills inside the midpoint, i.e. price improvement or liquidity-providing fills. An effective half-spread **greater than the quoted half-spread** means the order consumed more than the displayed size at the inside quote and swept deeper price levels. |
| **Quoted half-spread** (`QUOTED_HS`) | half the quoted bid–ask spread at order arrival, in bp of the midpoint (`QUOTED_HALF_SPREAD_BPS`; otherwise `ARR_SPREAD_BPS / 2`) | The cost of an immediate marketable execution of one displayed lot at arrival. Comparing it with the effective half-spread separates the spread that the name quotes from the spread the desk paid. |
| **Impact leg** (`IMPACT_LEG`) | Two measurements, depending on the order's execution duration (`DUR_HRS` × 60 compared with `--worked-minutes`, default 15 min). *Orders executed in under 15 minutes* ("prints"): the execution price against the interval VWAP, signed by side, the engine field `TEMP_IMPACT_BPS`. *Orders worked for 15 minutes or longer*: the realized half-spread of the order's fills at a 5-minute horizon minus the effective half-spread of the same fills, i.e. the price reversion after the fills (§2.3). | For prints: the execution price relative to the volume-weighted price of the market during the interval; positive means the order executed worse than the interval's average trade. For worked orders: positive means the midpoint moved back towards the pre-trade level after the fills (temporary impact, the cost of immediacy); negative means the midpoint continued in the direction of the trade after the fills (price continuation, which is counted in the trend and in the implementation shortfall, not in the liquidity tax). |
| **Liquidity tax** (`LIQ_TAX`) | effective half-spread (quoted half-spread if missing) + impact leg, clipped to ±200 bp per order (`--tax-clip`). `LIQ_TAX_RAW` is the unclipped value. | The cost of taking liquidity in the name, before any peer comparison. For a worked order the two terms combine to the realized half-spread: fill price against the midpoint 5 minutes after the fill. The clip exists because OTC quotes with a recorded spread of 0.0 produce effective half-spreads of several hundred basis points that are quote defects rather than execution costs. |
| **Trend** (`trend bps`) | `IS_BPS` − `IMPACT_LEG` per order | The component of IS not attributed to the impact leg: the movement of the price between arrival and execution, plus the effective half-spread (which is not part of the impact leg). Trend is therefore not equal to IS minus the liquidity tax; the two differ by the effective half-spread. |
| **Alpha** (`ALPHA_BPS`) | `IS_BPS` − the fitted value of `tca_core.fit_cost_model`, re-estimated on the slice; when a market-drift proxy exists (`MKT_DRIFT_PROXY_BPS`), the market move in the trade direction (side × proxy) is added as a regressor | The IS residual after the expected-cost regression's covariates. Positive: the order cost more than the model predicts for orders with the same characteristics. The model's R² on the slice is shown in a KPI tile and in the method section. |
| **Permanent impact** (`perm impact bps`) | the engine field `PERM_IMPACT_BPS` from `tca_core`, dollar-weighted per name | Reported in `tickers.csv` for reference; it is not used in any flag. |
| **Hit rate** (`hit rate %`) | share of the name's orders with `IS_BPS` < 0 | The fraction of orders that executed better than the arrival price. |

### 2.3 Mark-outs for worked orders

The impact leg of worked orders comes from a fill-level mark-out computed by the SQL in `MARKOUT_BY_TICKER_SQL`:

- **Fills considered.** The fills of the slice's orders whose execution duration (`ORDER_EXEC_DURATION_TS`) is at least `--worked-minutes`, with a positive fill price, within the window extended by five calendar days on each side.
- **Quote tape.** The script does not use an external quote feed. It reconstructs a midpoint tape per ticker from the bid and ask stamped on **all** fill records of that ticker in the window (`ORDER_BID_PRC`, `ORDER_ASK_PRC`, bid > 0, ask ≥ bid). The tape therefore has a point wherever the desk had a fill in the name, and nowhere else.
- **Mark-out.** For each fill at time t, the reference midpoint is the last tape point at or before t + 5 min (`--markout-min`) that is strictly after t and no more than max(30, 5 × 30) = 150 seconds before t + 5 min. `realized = side × (fill price − reference midpoint) / fill price × 10⁴`. Fills with no tape point in that interval have no mark-out.
- **Per-name aggregates** (table `markouts`): `realized_bps` (dollar-weighted realized half-spread over the covered fills), `eff_bps` (dollar-weighted effective half-spread of the same covered fills), `coverage_pct` (the covered fills' share of the name's worked-fill dollars), `notional`, `n_fills`, and `impact_mo_bps = realized_bps − eff_bps`.
- **Use in the liquidity tax.** A worked order takes its name's `impact_mo_bps` as impact leg when the name's `coverage_pct` is at least 20 % (`--markout-cov`); the flag `MO_COVERED` records this. Worked orders in names below the coverage threshold receive the dollar-weighted `impact_mo_bps` of the covered worked orders in the same participation band × volatility tercile (at least 50 orders), otherwise of the same band (at least 50 orders), otherwise of all covered worked orders. This imputed value is the cohort's own level, so it contributes nothing to the name's liquidity excess. If the fills store is unavailable, the query fails, or `--no-markouts` is passed, worked orders carry an impact leg of zero and their liquidity tax is the effective half-spread alone; the method section states which case applied, and `slice.json` records `worked_orders`, `markout_covered_orders` and `markout_imputed_orders`.
- **Interpretation of the sign.** Write M₀ for the midpoint at the fill and M₅ for the midpoint 5 minutes later. Then realized − effective = side × (M₀ − M₅) / price, up to the choice of denominator. A positive value means the midpoint moved against the direction of the trade after the fill (for a buy, the price fell back): the fill was executed at a temporarily elevated price, the spread paid was not recovered by the subsequent price path, and the liquidity provider on the other side earned a positive realized spread. This is the temporary component of price impact and is the pure cost of immediacy. A negative value means the midpoint continued in the direction of the trade (for a buy, the price kept rising): the fill was followed by price continuation, which can be the order's own permanent footprint, momentum in the name, or information arriving. That continuation is not a cost of liquidity in this decomposition; it is captured by the trend and by the implementation shortfall. In the 2026-09-30 run (v1.1 definitions) the dollar-weighted `impact_mo_bps` across covered names was +0.9 bp and the median +0.95 bp, i.e. mild reversion after the desk's worked fills on average.
- **The `impact source` column** describes a **name**, not an order. It is `vwap` when less than 50 % of the name's dollars are in worked orders; otherwise it is `mark-out` when at least one worked order of the name is tape-covered, and `cohort mark-out (no tape)` when none is. The column tells the reader which measurement dominates the name's impact leg.

Reason for the two measurements: for an order worked over several hours, the execution price relative to the interval VWAP measures how the fills were timed within the interval, not what the fills cost in terms of spread and short-horizon reversion. The 5-minute mark-out measures the latter directly.

### 2.4 Size: the platform's daily participation rate

The SMA platform trades a name through many account-level orders on the same day, each small relative to average daily volume. The relevant size for market impact is the aggregate of that flow. For every name-day the script computes

`DAY_PART = Σ filled shares of the platform's orders in the name that day / ADV × 100`,

where filled shares are `SHARES_FILLED` (or `ORDER_QTY` where missing) summed over all orders regardless of side, and ADV is `ADV_IMPLIED`, the average daily volume implied by the orders' own `%ADV` field, taken as the median across the name-day's orders (if `ADV_IMPLIED` is absent, ADV = `ORDER_QTY` / (`PCT_ADV` / 100)). `DAY_PART` is the platform's gross participation rate in the name for that session, in percent of ADV.

Participation bands (`--adv-bands`, edges in percent): `<0.1`, `0.1–0.5`, `0.5–2`, `2–5`, `5–15`, `15–50`, `>50`. Each band is closed on the left and open on the right. An order's band is the band of its name-day's `DAY_PART`; where that is missing, the band of the order's own `PCT_ADV` is used instead. `--cohort-size order` switches the cohort definition, the `by_band` table, chart 4.5 and the `band` column to the order's own `%ADV` (the v1.1 definition); the cost curves and the participation columns continue to use `DAY_PART`.

Two qualifications apply when reading participation rates. First, `DAY_PART` is gross flow (buys plus sells); the net quantity the market has to absorb can be smaller when accounts trade in both directions on the same day. Second, for OTC lines of foreign ordinaries and OTC-traded ADRs, `ADV_IMPLIED` refers to the US line, so a day in the `>50` band usually means that the broker sourced liquidity in the home market rather than that the platform was more than half of the US line's volume.

### 2.5 Peer cohorts, baselines and excesses

**Volatility tercile (`σ tercile`).** Each order's daily volatility (`DAILY_VOL_BPS`) is ranked across all orders of the slice and split into three groups of equal order count: `low σ`, `mid σ`, `high σ`. A name's tercile in the per-name tables is the modal tercile of its orders.

**Cohort.** The cohort of an order is the set of orders in the slice with the same participation band and the same volatility tercile.

**Leave-one-name-out baseline.** For each order, the baseline for a cost measure is the dollar-weighted mean of that measure over the orders of its cohort **excluding every order of the same ticker**, provided at least 100 such orders exist. If fewer than 100 remain, the baseline is computed over the band alone (again excluding the ticker, at least 100 orders); if that also fails, over the whole slice excluding the ticker. The exclusion prevents a ticker that dominates its cohort from being compared with itself (in the v1.1 run, one OTC name was about a fifth of the `>50 %` band). Two baselines are computed: `COHORT_LIQ` for the liquidity tax and `COHORT_IS` for the implementation shortfall.

**Liquidity excess** = `LIQ_TAX − COHORT_LIQ` per order; per name, the dollar-weighted mean (`liq excess bps`) and its dollar equivalent (`liq excess $` = `liq excess bps` / 10⁴ × notional). It is the part of the name's liquidity-taking cost that is not explained by the participation band and the volatility tercile. It is the screening variable of the whole report.

**IS excess** = `IS_BPS − COHORT_IS` per order; per name `IS excess bps`, `IS excess $`. It contains the drift of the price during the life of the orders, which the desk does not control, so it is a secondary variable in the classification.

**Kind.** For non-thin names, `kind` states how much of the IS excess the liquidity excess accounts for:
- `not expensive`: liquidity excess < 5 bp and IS excess < 5 bp;
- `liquidity`: the IS excess is not positive, or the ratio liquidity excess / IS excess is at least 0.5;
- `mixed`: the ratio is between 0.25 and 0.5;
- `drift`: the ratio is below 0.25;
- blank when either excess is undefined.

### 2.6 Name-day aggregation and day-level t-statistics

For every name the script builds a table with one row per trading day: the day's filled dollars, the day's participation rate, and the dollar-weighted liquidity tax, liquidity excess, IS excess and IS of the day's orders. The columns `liq excess day-mean bps` and `IS excess day-mean bps` are the unweighted means of these daily values, and every t-statistic in the report (`liq excess t`, `IS excess t`, `IS t`, and the recent-period variants) is the mean of the daily values divided by their standard error, with each day counting once. A t-statistic requires at least 5 days (3 in the recent lens), and the daily standard deviation is floored at `--se-floor` = 0.1 bp so that a name with near-identical daily values does not produce an unbounded t. The dollar-weighted excess remains the ranking variable; the day-level t only establishes whether the daily evidence supports the sign of the excess without being dominated by a few large days.

### 2.7 The cost curve

**Specification.** For every name with at least max(`--min-days`, 8) name-days with a positive participation rate and a defined liquidity tax, the script fits by ordinary least squares, one observation per name-day, unweighted:

`liquidity tax of the day = a + b × √(DAY_PART)`,

with `DAY_PART` in percent. The fitted slope `b` is in bp per √%. The square-root form is the standard participation-rate impact model; the intercept plays the role of the spread cost at vanishing participation.

**Identification requirement.** The name's own slope (`slope ols`, with `slope SE`) is retained only when its participation rates vary enough to identify a slope: the 90th percentile of `DAY_PART` must be at least twice the 10th percentile. Otherwise `slope ols` is left undefined and the name receives its cohort's slope. `curve days`, `curve R²` and `intercept ols` describe the raw fit.

**Cohort curves.** The same regression is fitted on all name-days of each security type × volatility tercile (the name's modal tercile), and on the whole slice (`type = all`). These are reported in `cohort_curves` with `intercept bps`, `slope bps per √%`, `slope SE`, `R²`, `name-days`, `names`.

**Shrinkage.** The reported `slope` is a precision-weighted combination of the name's own OLS slope and its cohort's slope:

`slope = (slope_ols / SE² + cohort slope / τ²) / (1 / SE² + 1 / τ²)`.

τ² is the between-name variance of the OLS slopes net of their sampling variance. It is estimated on the names with at least 20 curve days (on all fitted names when fewer than 20 such names exist): with at least 20 qualifying names, τ² = max(var(slope ols) − mean(SE²), (0.25 × sd(slope ols))², floor); with 3 to 19 names, τ² = max(var(slope ols), floor); with fewer, τ² = floor. The floor is (0.5 × |slice slope| + 1 bp)², so the prior is never tighter than half the slice slope plus one basis point. τ is reported as `shrinkage τ`. A name with an undefined `slope ols` has zero precision and receives the cohort slope exactly.

**Re-anchoring.** The reported `intercept` is set so that the shrunk line passes through the name's own centroid: `intercept = mean(daily tax) − slope × mean(√DAY_PART)`. The shrinkage therefore changes the steepness of the line but not its level at the participation rates the name actually traded.

**Derived quantities.**
- `p run`: the name's dollar-weighted daily participation rate over the curve's name-days (the participation rate the platform actually runs in the name).
- `cost at p run bps` = intercept + slope × √(p run): the fitted liquidity tax at the platform's own participation rate.
- `cohort cost at p run bps`: the cohort curve evaluated at the same participation rate.
- `excess at size bps` = cost at p run − cohort cost at p run: how much more the name costs than its peers at the size the platform trades it.
- `slope t vs cohort` = (slope ols − cohort slope) / slope SE: the statistical evidence that the name's cost rises with participation faster than its peers' does.
- `tc cost at 1% bps`, `tc cost at 5% bps`, `tc cost at 20% bps`: the shrunk curve evaluated at participation rates of 1 %, 5 % and 20 % of ADV, floored at zero. These three numbers are the per-ticker input for the two-pass transaction-cost model (first pass to estimate the platform's net flow per name, second pass with the per-name cost evaluated at that flow), in place of the flat 30 bp linear cost currently in the Axioma workspaces.

**Relation to the engine's parameters.** In the square-root regime the curve corresponds to `s + θ σ √x` with x the participation rate as a fraction. Because the script measures participation in percent, √x = √p / 10 and a slope of `b` bp per √% corresponds to `θ σ = 10 b` bp. A slope of 10 bp per √% in a name with a 200 bp daily volatility therefore implies θ ≈ 0.5. A negative intercept indicates fills executed inside the spread (passive or midpoint executions) at low participation; the transaction-cost model floors it at zero.

### 2.8 Flags and classifications

All flags are evaluated on non-thin names only.

| flag | rule |
|---|---|
| `wide spread` | effective half-spread ≥ max(8 bp, 90th percentile of the effective half-spread among the non-thin names of the same participation band) |
| `impact` | impact leg ≥ max(3 bp, 90th percentile among the non-thin names of the same band) |
| `expensive to trade` | liquidity excess ≥ 5 bp **and** day-level t of the liquidity excess ≥ 2 |
| `expensive at size` | not `expensive to trade`; liquidity excess ≥ 5 bp; `excess at size bps` ≥ 5 bp; `slope t vs cohort` ≥ 2 |
| `expensive vs peers` | IS excess ≥ 5 bp and day-level t of the IS excess ≥ 2 |
| `persistent` | at least 3 calendar months with ≥ 5 orders; median monthly liquidity excess ≥ 5 bp; at least 50 % of those months at or above 5 bp |
| `concentrated` | the largest single day accounts for ≥ 50 % of the name's filled dollars; appended to `reasons` as "(one day > 50 % of $)" |

The band-level 90th percentiles are computed within a band only when it contains at least 20 non-thin names; otherwise the slice-wide 90th percentile is used.

Derived classifications:
- `watch` = `expensive to trade` or `expensive at size`. **Only these two flags place a name on the watch list.** `wide spread` and `impact` are descriptive: they appear in `reasons` and in the counts of the watch-list reading, but a name with a wide spread whose liquidity excess is ordinary is not on the list.
- `how` = `wide` (expensive to trade), `wide + at size` (expensive to trade, and in addition `excess at size bps` ≥ 5 bp with `slope t vs cohort` ≥ 2), or `at size` (expensive at size only).
- `priority` = `portfolio side` when the name is on the watch list and `persistent`; `watch` otherwise. "Portfolio side" marks names whose excess cost recurs month after month and should be addressed with the portfolio construction team (participation limits in the optimiser, cost-model inputs, exclusion as a last resort) rather than by routing changes alone.
- `drift name` = `expensive vs peers`, `kind` = `drift`, and not on the watch list.
- `reasons`: the flags that fired, comma-separated, plus the concentration note. `flags`: the number of flags fired (0–6).

### 2.9 Persistence and concentration

The order flow is aggregated by ticker × calendar month, keeping months with at least 5 orders (`monthly` table). Per name: `months` (count of such months), `median month liq excess bps`, `months ≥ threshold %` (share of months with liquidity excess ≥ 5 bp), and the equivalents for IS excess (`median month IS excess bps`, `months IS ≥ threshold %`). The `persistent` flag uses the liquidity columns.

`top day share %` is the largest single day's share of the name's dollars, and `top order share %` the largest single order's share. A name whose evidence is concentrated in one day should be re-examined on later runs before any action.

### 2.10 The recent lens

The recent lens re-measures every name over the last `--recent-days` = 20 trading days of the window (the lens is disabled when the window does not contain more than 20 trading days).

**Construction.** The recent orders keep their window cohort baselines (`COHORT_LIQ`, `COHORT_IS`), so a name is judged against the same peer levels as over the window. The slice's own dollar-weighted excess over the recent days is then subtracted from every order's excess (`recent_shift_bps` in `slice.json`, printed in the section header), so that a market-wide change in spreads or volatility over the recent period does not turn every name into a mover. Recent t-statistics use the day-level construction of §2.6 with a minimum of 3 days.

**Eligibility.** A name is assessed in the lens when it has at least 8 recent orders (`--recent-min-orders`) on at least 3 recent days and at least the recent dollar floor, which is `--min-notional` scaled by (recent days / window days) unless `--recent-min-notional` is given.

**`recent $ / avg month`** = recent notional / (window notional / number of months with ≥ 5 orders). A value of 1 means the recent 20 days carried about one average month of flow; 0.3 means the flow in the name has shrunk to about a third of its usual monthly rate.

**Movers.**
- `turned expensive`: eligible; recent liquidity excess ≥ 5 bp with recent t ≥ 2; window notional ≥ $1M; and either the recent excess exceeds the window excess by at least 5 bp, or the name is too thin over the window (fewer than 20 orders or 5 days) to have a window verdict. The `change` label is `turned expensive` for a name with a window verdict, `new and expensive` for a name without one, and `on the list, getting worse` for a name already on the watch list.
- `improving`: on the watch list; eligible; recent liquidity excess < 5 bp; at least 5 bp below the window excess; `recent $ / avg month` ≥ 0.5. Label: `improving (on the list, normal lately at normal size)`.
- `traded less lately`: on the watch list; has recent orders; `recent $ / avg month` < 0.5; recent liquidity excess < 5 bp. Label: `traded less lately (on the list; recent $ under half an average month)`. The lower recent excess of such a name is attributable to the smaller flow, so the name is not counted as improving; names that are expensive at size behave this way whenever the platform trades them less.

**Recent drift** (`recent_drift` table): eligible names with recent IS excess ≥ 5 bp, recent IS t ≥ 2, and recent liquidity excess < 5 bp; the fifteen largest by recent IS-excess dollars.

### 2.11 Baseline comparison and daily bookkeeping

With `--baseline <path>` pointing at a previous run's `tables/watchlist.csv` (or its `slice.json`), the script reports the names that entered and left the watch list, carries forward `first seen` (the run date on which the name first appeared) and increments `runs on list` (consecutive runs on the list). In `--daily` mode the previous dated folder is the baseline automatically.

`history.csv` receives, for each run date, one row per name that is on the watch list, is a drift name, or is a mover, with a `status` in {`watch`, `watch, improving`, `watch, traded less lately`, `watch, getting worse`, `drift`, `turned expensive`, `new and expensive`}, the key cost and size columns, `reasons`, `first seen`, `runs on list`. Re-running the same date replaces that date's rows. `runs.csv` receives one row per run with the slice statistics and the list sizes.

---

## 3. The tables

Tables are listed in the order of the report. Column names are given exactly as written in the CSV headers.

### 3.1 `by_type` — the slice by security type

Columns: `security type`, `n` (orders), `Notional`, `names`, `%ADV $-w` (dollar-weighted order-level %ADV), `day participation $-w %` (dollar-weighted platform daily participation rate), `IS bps`, `IS winsorised`, `trend` (= `IS bps` − `impact`), `eff ½-spread`, `quoted ½-spread`, `impact`, `liquidity tax`, `alpha`. All in bp, dollar-weighted. Sorted by notional.

Interpretation. `liquidity tax` is the part of the implementation shortfall attributable to taking liquidity (spread plus short-horizon impact); the remainder of `IS bps` is price movement during the orders' lives. A security type whose IS is mostly trend has a scheduling and urgency question, not an execution-quality question. The report compares the two largest types and, when their liquidity taxes differ by more than 2 bp, raises a finding ("<type A>s pay a higher liquidity tax than <type B>s") and refers the reader to `by_band` to determine whether the gap comes from the names (spread and depth) or from the participation rates at which the two types are traded. For scale, the 2026-09-30 year-to-date run under v1.1 definitions showed a slice IS of +10.4 bp against a liquidity tax of 3.4 bp (ADRs 7.2 bp, common stocks 2.8 bp).

### 3.2 `by_band` — the slice by participation band and security type

Columns: `band`, `security type`, `n`, `Notional`, `IS bps`, `eff ½-spread bps`, `quoted ½-spread bps`, `impact bps`, `liquidity tax bps`, `share of $ %`.

Interpretation. The table shows how the liquidity-taking cost rises with the platform's participation rate and where the traded dollars sit. Two comparisons matter for the desk: the band in which `eff ½-spread bps` rises above `quoted ½-spread bps` (from that participation rate onwards, the platform's flow consumes more than the displayed depth at the inside quote), and the band in which `impact bps` becomes material. A band with a high liquidity tax and a small share of dollars indicates a few expensive names; a band that holds most of the dollars and shows a rising tax indicates that the platform's aggregate size is the cost driver.

### 3.3 `cohorts` (CSV only)

Columns: `band`, `σ tercile`, `n`, `Notional`, `IS bps`, `eff ½-spread bps`, `impact bps`, `liquidity tax bps`, `names`. Plain dollar-weighted means per cohort, for reference. The baselines applied to individual names are the leave-one-name-out versions of §2.5, which differ from these means for names that are a large share of their cohort.

### 3.4 `markouts` (CSV only)

Columns: `TICKER`, `realized_bps`, `eff_bps`, `coverage_pct`, `notional`, `n_fills`, `impact_mo_bps`, as defined in §2.3; sorted by notional.

Interpretation. This is the fill-quality table for worked orders. `realized_bps` is the fill price against the midpoint 5 minutes later (positive = cost). `impact_mo_bps` > 0 (realized above effective) means the price reverted after the desk's fills: the fills were executed at temporarily unfavourable prices and the spread paid was not recovered, which is the pure cost of immediacy and points at the aggressiveness of the child orders (clip size, marketable order share, venue). `impact_mo_bps` < 0 means the price continued in the direction of the trade after the fills, which is momentum or permanent impact and is not a liquidity-taking cost in this decomposition. A low `coverage_pct` means the desk's own fill records rarely bracketed the fills within the 150-second tolerance, which happens in names traded sparsely; those names run on their cohort's mark-out (§2.3). Two columns of this table are repeated in `tickers.csv` as `realized ½-spread +5m bps (worked)` and `mark-out coverage %`.

### 3.5 `watchlist` — the main table

Rows: every non-thin name with `watch` true, sorted by `liq excess $` descending. Columns, by group:

| group | columns |
|---|---|
| identity and verdict | `TICKER`, `type`, `sector`, `priority`, `how`, `kind`, `reasons`, `first seen`, `runs on list` |
| size | `orders`, `days`, `notional`, `day participation $-w %`, `%ADV $-w`, `band` (band of the name's dollar-weighted daily participation rate), `worked share of $ %` |
| liquidity | `liquidity tax bps`, `cohort liquidity tax bps`, `liq excess bps`, `liq excess day-mean bps`, `liq excess t`, `liq excess $`, `eff ½-spread bps`, `quoted ½-spread bps`, `impact bps`, `impact source` |
| cost curve | `curve days`, `curve R²`, `intercept`, `slope`, `slope t vs cohort`, `cost at p run bps`, `cohort cost at p run bps`, `excess at size bps`, `tc cost at 1% bps`, `tc cost at 5% bps`, `tc cost at 20% bps` |
| recent lens | `recent liq excess bps`, `recent liq excess t`, `recent $ / avg month` |
| implementation shortfall | `IS bps`, `trend bps`, `IS excess bps`, `IS excess t`, `IS excess $`, `alpha bps` |
| persistence and concentration | `months`, `median month liq excess bps`, `months ≥ threshold %`, `top day share %` |

How to read a row.
1. `how` and `kind` give the diagnosis. `wide` with `kind = liquidity`: the name costs more than its peers at every participation rate because of its spread and depth; compare `eff ½-spread bps` with `quoted ½-spread bps` (sweeping beyond the inside quote) and look at `impact bps` and `impact source`. `at size` with `kind = liquidity`: the name is in line with its peers at low participation and more expensive than they are at the participation rate the platform runs; `slope t vs cohort` gives the evidence, `excess at size bps` the size of the gap at `p run`, and chart 4.3 shows the participation rate at which the name's curve leaves the cohort's. `kind = mixed` or `drift` on a watch-list name: a material part of the IS excess is price movement during the orders' lives, which the execution desk does not control.
2. `priority`. `portfolio side` means the liquidity excess has been present in most months: the cost is a property of the name at the platform's sizes and should be taken to portfolio construction. `watch` means the excess is established over the window but not yet persistent across months.
3. The recent-lens columns say whether the name is still expensive over the last 20 trading days and whether the recent flow is comparable to the usual monthly flow.
4. `top day share %` close to 100 means the window's evidence rests on one day.
5. `tc cost at 1% / 5% / 20% bps` are the numbers the transaction-cost model consumes for this name.

The report's reading paragraph sums the list: dollars traded and their share of the slice; liquidity-excess dollars and the same in bp of the list's own dollars; the list's dollar-weighted liquidity tax and participation rate against the slice's; the counts of wide, at-size, persistent, wide-spread, impact-flagged and one-day names; the counts by `kind`; the number of names whose effective half-spread exceeds their quoted half-spread; and the five largest names with their `tc cost` values. The finding "N names are expensive to trade: $X of liquidity tax beyond their cohorts" is marked at the higher of the report's two severity levels when X exceeds 0.05 % (5 bp) of the slice's traded dollars. The recommendations are: (a) use the per-name curve in the TC model instead of a flat cost; (b) address the portfolio-side names first; (c) for the at-size names, reduce the platform's daily participation rate (spread the flow over more sessions, cap the percentage of volume) before considering exclusion; (d) for the names paying more than the quoted half-spread, the child-order size exceeds the displayed depth; (e) names on the list for 20 or more consecutive runs (one month of daily runs) are to be raised with portfolio construction.

### 3.6 `changes` — entries and exits against the baseline

Columns: `TICKER`, `change` (`entered` / `left`), `how`, `liq excess bps`, `recent liq excess bps`, `kind`, `reasons` (for a name that left and is absent from the current window: "not in this window"). Produced when a baseline is given or in `--daily` mode. The reading paragraph counts entries, exits and names that stayed.

### 3.7 `cohort_curves`

Columns: `type`, `σ tercile`, `name-days`, `names`, `intercept bps`, `slope bps per √%`, `slope SE`, `R²`; one row per security type × volatility tercile plus one row for the slice (`type = all`). The reading paragraph evaluates the slice curve at participation rates of 1 %, 5 % and 20 % and lists each cohort's intercept and slope. These curves are the transaction-cost model's default for names without a curve of their own, and the shrinkage target for names with one.

### 3.8 `cost_curves`

Rows: every name with a fitted curve, sorted by `excess at size bps` descending (the report shows the top `--top`; the CSV holds all). Columns: `TICKER`, `type`, `priority`, `how`, `notional`, `day participation $-w %`, `curve days`, `curve R²`, `intercept`, `slope`, `slope ols`, `slope SE`, `slope t vs cohort`, `cohort intercept`, `cohort slope`, `p run`, `cost at p run bps`, `cohort cost at p run bps`, `excess at size bps`, `tc cost at 1% bps`, `tc cost at 5% bps`, `tc cost at 20% bps`, `liq excess bps`, `liq excess t`, `shrinkage τ`.

Interpretation. `slope` against `cohort slope` states whether the name's liquidity-taking cost grows with participation faster than its peers'; `slope t vs cohort` gives the evidence; `curve R²` and `curve days` state how much of the day-to-day variation in the tax the participation rate explains and on how many days. The reading paragraph counts the names with `slope t vs cohort` ≥ 2 and lists the eight largest by `excess at size bps` among those that are **not** on the watch list and have at least $1M traded: these are names whose cost is still acceptable at today's participation rates but would rise faster than their peers' if the platform's flow in them increased. For the transaction-cost model, the three `tc cost` columns are the deliverable of this table.

### 3.9 `drift_names` — expensive on implementation shortfall, not on liquidity

Rows: non-thin names with `expensive vs peers` true, `kind = drift`, and not on the watch list; sorted by `IS excess $` descending; the report shows the top `--top`. Columns: `TICKER`, `type`, `sector`, `orders`, `days`, `notional`, `day participation $-w %`, `buy share %`, `IS bps`, `trend bps`, `IS excess bps`, `IS excess t`, `IS excess $`, `liquidity tax bps`, `liq excess bps`, `liq excess t`, `eff ½-spread bps`, `impact bps`, `months`, `median month IS excess bps`, `months IS ≥ threshold %`, `top day share %`.

Interpretation. These names cost more than their peers on an arrival-price benchmark while their spread and short-horizon impact are ordinary. The excess is price movement between arrival and execution: the signal materialising while the orders are being worked, market moves, or the platform's own footprint on days when it is a large share of the volume. `months IS ≥ threshold %` says whether the adverse drift recurs every month. The appropriate response is a review of order timing and urgency (schedule length, time of day, how fast the model's trade list is released) with portfolio construction; the names are not inputs for the spread term of the transaction-cost model and are not a routing or venue issue. The report raises the finding "N names are expensive on IS but not to trade — $X of drift".

### 3.10 `recent_movers`

Rows: names flagged `turned expensive`, `improving` or `traded less lately`, in that order, each group sorted by `recent liq excess $`. Columns: `TICKER`, `type`, `change` (label, §2.10), `how`, `kind`, `orders`, `recent orders`, `recent days`, `recent notional`, `recent $ / avg month`, `recent participation %`, `day participation $-w %`, `liq excess bps`, `recent liq excess bps`, `recent liq excess t`, `recent liq excess $`, `liquidity tax bps`, `recent liquidity tax bps`, `eff ½-spread bps`, `recent eff ½-spread bps`, `recent IS excess bps`, `watch`, `reasons`.

Interpretation. Each row places the window figure next to the recent figure for the liquidity excess, the liquidity tax, the effective half-spread and the participation rate, so the reader can see whether a change in cost came with a change in size (`recent participation %` against `day participation $-w %`, `recent $ / avg month`) or in spread. The recent t-statistic is computed on at most 20 days; a mover should be confirmed on subsequent runs before action is taken. The report's finding "N names turned expensive to trade over the last 20 trading days" lists the names and the recent excess dollars.

### 3.11 `recent_drift`

Columns: `TICKER`, `type`, `recent orders`, `recent notional`, `recent $ / avg month`, `recent IS bps`, `recent IS excess bps`, `recent IS excess t`, `recent IS excess $`, `recent liq excess bps`, `recent liquidity tax bps`, `liquidity tax bps`, `IS excess bps`, `watch`. The fifteen names with the largest recent IS-excess dollars among eligible names whose recent liquidity excess is below 5 bp: the arrival-price cost rose over the recent period while the liquidity-taking cost did not. This table is for portfolio construction (timing and urgency), not for the desk.

### 3.12 `tickers` — every name

Rows: all names in the slice, including thin ones, sorted by `liq excess $` descending (the report shows the top `--top`). Columns: all columns of the tables above plus `σ tercile`, `buy share %`, `%ADV median`, `day participation median %`, `temp impact (VWAP) bps`, `liquidity tax raw bps`, `slope ols`, `slope SE`, `cohort intercept`, `cohort slope`, `IS t`, `IS winsorised bps`, `IS median order bps`, `hit rate %`, `perm impact bps`, `cohort IS bps`, `IS excess day-mean bps`, `median month IS excess bps`, `months IS ≥ threshold %`, `top order share %`, the complete set of recent-lens columns, `realized ½-spread +5m bps (worked)`, `mark-out coverage %`, `thin`, `flags`, and the boolean columns `watch`, `drift name`, `turned expensive`, `improving`, `traded less lately`. This is the reference table for questions about a specific name; it is meant to be filtered, not read top to bottom.

### 3.13 `monthly` (CSV only)

Columns: `TICKER`, `month`, `n`, `Notional`, `liq excess bps`, `IS excess bps`, `liquidity tax bps`, `IS bps`, `day participation %`; ticker × calendar month with at least 5 orders. Source of the persistence columns and of the persistence heatmap.

### 3.14 `cheapest_vs_peers`

Rows: non-thin names with `liq excess t` ≤ −2, the fifteen with the most negative `liq excess $`. Columns: `TICKER`, `type`, `orders`, `notional`, `day participation $-w %`, `liquidity tax bps`, `liq excess bps`, `liq excess t`, `liq excess $`, `tc cost at 5% bps`, `IS excess bps`. These names take liquidity more cheaply than their peers with statistical support. For the transaction-cost model they are the low end of the per-ticker cost distribution. For the desk they are a control group: if the names here share a routing, venue or algorithm pattern that the watch-list names do not, that pattern is evidence about what is working.

### 3.15 `slice.json`, `history.csv`, `runs.csv`

`slice.json` keys: `version`, `start`, `end`, `window`, `sec_types`, `orders`, `notional`, `names`, `names_screened`, `cohort_size`, `slice_is_bps`, `slice_liquidity_tax_bps`, the lists `watchlist`, `wide`, `at_size`, `portfolio_side`, `drift_names`, `turned_expensive`, `improving`, `traded_less_lately`, `entered`, `left` (arrays of tickers), `recent_days`, `recent_shift_bps` (liquidity and IS), `recent_floor_usd`, `baseline`, `daily`, `worked_orders`, `markout_covered_orders`, `markout_imputed_orders`, `spread_lens`, `slice_curve` (intercept and slope), `thresholds`, `cost_model_r2`, `generated`. The file is the machine-readable summary for downstream scripts and for the `--baseline` option.

`history.csv` columns: `date`, `TICKER`, `type`, `status`, `priority`, `how`, `kind`, `orders`, `notional`, `day participation $-w %`, `liquidity tax bps`, `liq excess bps`, `liq excess t`, `liq excess $`, `excess at size bps`, `tc cost at 5% bps`, `IS excess bps`, `IS excess $`, `recent orders`, `recent $ / avg month`, `recent liq excess bps`, `recent liq excess t`, `eff ½-spread bps`, `impact bps`, `reasons`, `first seen`, `runs on list`. One row per flagged name per run date (§2.11).

`runs.csv` columns: `date`, `generated`, `version`, `window_start`, `window`, `orders`, `notional`, `names`, `names_screened`, `slice_is_bps`, `slice_liq_tax_bps`, `watch`, `wide`, `at_size`, `watch_liq_excess_usd`, `portfolio_side`, `drift_names`, `entered`, `left`, `turned_expensive`, `improving`, `traded_less`, `liq_tax_watch_bps`, `recent_from`, `baseline`, `report`. One row per run: the time series of the screen's own aggregates.

---

## 4. The charts

All charts are drawn on non-thin names unless stated. Values are clipped for display only; the tables hold the unclipped values.

**4.1 `spread_vs_excess`.** One marker per name. x: dollar-weighted effective half-spread, symmetric-log scale (linear between −2 and +2 bp), clipped to [−20, 100] bp; negative values are fills inside the midpoint. y: liquidity excess against the cohort, clipped to ±100 bp. Colour: security type. Marker size increases with notional. The twenty largest watch-list names are labelled. Reading: names in the upper right pay a wide effective spread and are expensive relative to peers (spread-driven); names in the upper left are expensive relative to peers while paying a tight effective spread, which places the cost in the impact leg or in the platform's size rather than in the quote, and these are the names the desk can act on through participation and aggressiveness; names below the zero line take liquidity more cheaply than their peers.

**4.2 `is_vs_liquidity`.** x: IS excess; y: liquidity excess; both clipped to ±100 bp. Colour: `kind` (grey not expensive, red liquidity, orange mixed, blue drift). The dotted diagonal is y = x. The ten largest watch-list names and the eight largest drift names are labelled. Reading: a name on or near the diagonal is expensive on the arrival-price benchmark because it is expensive to take liquidity in; a name far to the right of the diagonal and close to the x-axis has an IS excess made of price movement during the orders' lives. The desk's names are near the diagonal; the drift names lie along the x-axis.

**4.3 `cost_curves`.** Up to twelve panels, one per watch-list name with a fitted curve, in watch-list order. In each panel: one marker per trading day at x = √(daily participation rate in %) and y = the day's liquidity tax (clipped to [−100, 300] bp), marker size increasing with the day's dollars; the name's shrunk curve in red; the cohort curve dashed grey; a dotted orange vertical at √(`p run`). The panel title gives `how`, the name's slope against the cohort's, and `p run`. Reading: a red line above the grey line over the whole range indicates a wide name; a red line that coincides with the grey line at low participation and rises above it at higher participation indicates an at-size name, and the dotted vertical shows the participation rate at which the platform operates on that curve. The spread of the markers shows whether the slope is supported by many days or by a few.

**4.4 `recent_vs_window`.** x: liquidity excess over the window; y: liquidity excess over the last 20 trading days; both clipped to ±100 bp. Grey markers: names with at least 8 recent orders and recent dollars above the recent floor; red: `turned expensive`; green: `improving`; orange: `traded less lately`. Marker size increases with recent notional. The twelve largest turned-expensive and eight largest improving names are labelled. Reading: a name above the diagonal is more expensive relative to peers over the recent period than over the window; a name below it is less expensive. This is the chart to inspect on daily runs.

**4.5 `spread_by_size`.** Three bar panels with the participation bands on the x-axis and bars per security type: quoted half-spread, effective half-spread paid, liquidity tax (effective half-spread plus impact leg). Reading: the bands in which the effective bars exceed the quoted bars are the participation rates from which the platform's flow consumes more than the displayed depth; the liquidity-tax panel shows the bands in which the impact leg becomes the larger component.

**4.6 `persistence`.** A heatmap of the monthly liquidity excess (clipped to ±100 bp) for the twenty-five largest watch-list names, one row per name and one column per calendar month; drawn only when the window spans at least two months. Reading: a row that is red in every month identifies a name whose excess cost is structural at the platform's sizes; a row with a single red cell identifies a one-month episode.

**4.7 `excess_dollars`.** Two bar panels over the twenty-five largest non-thin names by liquidity-excess dollars. Top panel: `liq excess $` per name, red for watch-list names and grey for the others. Bottom panel: the same names' drift dollars, defined as `IS excess $` − `liq excess $`, blue when positive (price movement added cost) and green when negative (price movement reduced cost). Reading: the top panel ranks the names by the dollar cost of taking liquidity beyond their peers; the bottom panel shows, for the same names, whether price movement during the orders' lives added more or less than the liquidity-taking cost did.

---

## 5. Reading order for the execution desk

The execution desk controls how a name is traded: venue and routing, algorithm and its aggressiveness, child-order size, the share of daily volume the platform takes, and the number of sessions over which the aggregate flow is spread. It does not control what is traded or when the trade list is generated; those decisions belong to the model and to portfolio construction. The outputs divide along that line.

### 5.1 Outputs to review on every run

1. **`watchlist`, filtered to `kind = liquidity`, in its own order (`liq excess $` descending).** These are the names whose cost above peers sits in the spread paid and in the impact leg, i.e. in the execution itself.
   - Names with `how = at size` or `wide + at size`: the cost is a function of the platform's participation rate. The actions available to the desk are a lower percentage-of-volume cap, a longer schedule (more sessions for the same aggregate quantity), and less aggressive child orders; `p run` compared with the point where the red curve leaves the grey one in chart 4.3 indicates how far the participation rate would need to fall.
   - Names with `eff ½-spread bps` > `quoted ½-spread bps`: the child orders consume more than the displayed size at the inside quote and sweep deeper levels. The actions are smaller clips, a larger passive or midpoint share, and a review of the venues used. The reading paragraph gives the count of such names.
   - Names with `impact source = mark-out` and a large positive `impact bps`: the worked orders' fills are followed by price reversion, so the desk is paying for immediacy that the subsequent price path does not justify. The `markouts` table gives `realized_bps`, `eff_bps` and `coverage_pct` for the name.
   - Names with `priority = portfolio side`: the excess cost recurs across months. Routing changes should still be attempted, but the name should also be raised with portfolio construction (participation limits in the optimiser, cost-model input, exclusion as a last resort).
2. **`recent_movers`, the `turned expensive` rows, together with chart 4.4.** The window excess of a name changes by hundredths of a basis point per day, so a deterioration appears in the recent lens several weeks before it can change the window classification. A mover should be acted on once it repeats on the following runs; `history.csv` keeps the sequence. A `traded less lately` name has not improved: its lower recent excess coincides with a smaller flow.
3. **`changes`** (baseline or `--daily` mode): the names that entered and left the watch list since the previous run. A `runs on list` value of 20 or more corresponds to one month of daily runs and is the threshold at which the report recommends escalation to portfolio construction.
4. **Chart 4.5 and `by_band`.** They show the participation rate from which the platform's flow consumes more than the displayed depth, and the rate from which the impact leg dominates, per security type. These are the data on which percentage-of-volume caps by band can be set.
5. **Chart 4.3 and `cost_curves`** when a specific name is under discussion: the curve gives the expected liquidity-taking cost of a larger block in that name and shows whether the slope is supported by many trading days. The names listed in the reading paragraph as steep but not on the watch list are those where an increase in the platform's flow would raise costs first.

### 5.2 Outputs to review periodically

- **`markouts`**: fill quality on worked orders by name (reversion against continuation; tape coverage). This table is the starting point for venue and algorithm reviews.
- **`cheapest_vs_peers`**: the control group; useful to test whether a routing or venue pattern distinguishes the cheapest names from the watch-list names.
- **`by_type`**: slice-level figures for reporting to management. The liquidity tax is the execution-quality figure; the trend is not.

### 5.3 Outputs that belong to portfolio construction

- **`drift_names`, `recent_drift`, the bottom panel of chart 4.7, and every `IS excess` and `alpha` column.** They measure price movement during the orders' lives, which is a question of urgency, schedule and the timing of the signal. A name that is expensive on implementation shortfall with an ordinary liquidity tax is not a routing problem; executing it more aggressively would raise its liquidity tax without removing the drift.
- **Chart 4.6 and `priority = portfolio side`**: the persistence of the excess cost is the basis for decisions on participation limits, cost-model inputs and exclusions.
- **`cohort_curves`, the `tc cost` columns of `cost_curves`, `watchlist` and `tickers`**: the inputs for the two-pass transaction-cost model.
- **`tickers`**: the reference table for both sides.

### 5.4 Cautions that apply to every output

- Compare names on their **excess** against cohorts rather than on the level of the liquidity tax. The level combines an effective half-spread with an impact leg measured in two different ways (interval VWAP for prints, 5-minute mark-out for worked orders); the peer comparison within the same band and tercile removes most of the consequences of that convention, the level does not.
- A name whose evidence comes from one day (`top day share %` ≥ 50, "(one day > 50 % of $)" in `reasons`) should be confirmed on later runs before any action.
- Recent-lens t-statistics are computed on at most 20 trading days and often fewer; treat a mover as a candidate until it repeats.
- An effective half-spread of exactly zero on an OTC line usually indicates a missing quote rather than a midpoint fill; the ±200 bp clip limits the effect of the resulting outliers but does not remove it, and `liquidity tax raw bps` shows what was clipped.
- The mark-out tape is built from the desk's own fill records, so the realized half-spread is measured only at times when the desk had another fill in the name within the tolerance window; `coverage_pct` states how representative that is.

---

## 6. Labelling defects in v1.2 (for a v1.3)

Found while reading the plotting code; none changes a reading, each is a one-line fix.

1. In the scatter charts (4.1, 4.2, 4.4) the marker area is `√(notional / 1e5) + 4`, so the area grows with the square root of the dollars (a name with four times the dollars has twice the area). The titles state "area ∝ $", which overstates the visual contrast between large and small names.
2. The title of chart 4.7 states "grey = thin or not significant", but thin names are excluded from that chart; grey means "not on the watch list".
3. The method text describes the worked-order impact leg as "each fill against the mid 5 min later on the desk's own quote tape, less the effective spread of the same fills" without stating the sign convention. The quantity is the price reversion after the fill (realized half-spread minus effective half-spread, §2.3): positive on reversion, negative on continuation. The text should state this, because the sign carries the interpretation.
