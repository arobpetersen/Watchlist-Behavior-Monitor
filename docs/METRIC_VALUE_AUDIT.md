# Metric Value Audit

Date: 2026-05-21

Scope: audit/design only. This document does not implement metric removals, calculation changes, page redesigns, new analytics, page-render data fetching, or LLM integration.

## Executive Summary

- Summary views should prioritize binary/survival questions over fuzzy magnitude metrics: success, active, D0/D1/D2/D3 failure timing, after-D3 failure, untriggered, and sample count.
- `Median Current %`, `Median Max %`, and `Median D3 High %` are useful context, but they should generally be secondary or detail-level, not primary summary anchors.
- Eligible D3 High is the only D3 follow-through metric suitable for summaries; raw D3 High should remain detail/audit only.
- The largest missing high-value metric family is failure timing distribution by window, trigger, and setup type.
- Trend-shift callouts should summarize deterministic changes in success/failure/survival before showing dense comparison tables.

## Metric Classification Table

| Metric | Current Pages | Current Role | Value Rating | Recommended Placement | Why | Suggested Replacement |
|---|---|---|---|---|---|---|
| Setups / Count / Sample | Daily Snapshot, Rolling, Window Overview, Setup Type Performance, Daily Report | Denominator/context | High | Primary | Every rate needs sample context within 5 seconds. | Keep; show beside rates. |
| Rows | Trigger Event Explorer | Filter result context | Medium | Secondary | Useful for filtered research, but not a quality signal. | Keep as filter context. |
| Triggered count | Trigger Event Explorer, Window Overview, Daily Report | Attempt/sample context | High | Primary when trigger-specific | Clarifies whether success/fail rates are meaningful. | Keep; pair with attempts/success. |
| Eligible count | Window Overview trigger tables | Applicability context | Medium | Secondary | Helps explain trigger denominators but can clutter top reads. | Keep in detail tables; top read can use Attempts. |
| Success % | Daily Trigger Read, Window Overview, Setup Type Performance, Explorer | Trigger/setup quality | High | Primary | Directly answers "is this working?" | Keep; gate with sample count. |
| Active % / Active count | Daily, Rolling, Window, Setup Type, Explorer, Report | Survival/current state | High | Primary | Direct signal that setups remain alive. | Keep; pair with failure timing. |
| D0 Fail % / D0 Fail count | Daily, Rolling, Setup Type, Report | Setup-day failure | High | Primary | One of the clearest risk/quality signals. | Keep; later separate from D1/D2/D3 timing. |
| Failed After D0 % / count | Daily, Rolling, Window, Setup Type, Explorer, Report | Later failure aggregate | Medium | Replace | Useful but too broad; hides D1 vs D2 vs D3 vs after-D3. | Failure Timing Distribution. |
| D1 Fail % | Proposed/missing | Failure timing | High | Primary | Answers when triggered setups stop out. | Add via failure timing helper. |
| D2 Fail % | Proposed/missing | Failure timing | High | Primary | Answers when triggered setups stop out. | Add via failure timing helper. |
| D3 Fail % | Proposed/missing | Failure timing | High | Primary | Important boundary for D3 follow-through validity. | Add via failure timing helper. |
| Failed After D3 % | Proposed/missing | Later survival | High | Primary | Separates survived-through-D3 failures from early failures. | Add via failure timing helper. |
| Unresolved / Untriggered % | Daily, Rolling, Window | No-trigger context | High | Primary/Secondary | Important for market participation and trigger availability. | Keep; label denominator clearly. |
| Close < BE | Daily, Rolling, Setup Type, Report, Explorer filters | Weak-close diagnostic | Medium | Secondary | Useful weakness signal, but less central than survival/failure timing. | Keep below primary read. |
| Retested / Retested D0 / Retested After D0 | Daily, Rolling, Setup Type, Report | Path/behavior diagnostic | Medium | Secondary | Useful context, but not a top quality verdict. | Keep secondary; trend only if material. |
| Current % | Row tables, Top Movers, Explorer | Current return magnitude | High in row/name pages, Low in summaries | Detail / Top Movers primary | Good for ranking names, weak as setup-quality summary due to timing and market movement. | Use Active %, failure timing in summaries. |
| Max % | Row tables, Top Movers, Explorer | Maximum excursion | High in row/name pages, Medium in research | Detail / Top Movers primary | Useful for top movers and follow-through research; fuzzy as top-level quality because outliers/volatility dominate. | Use reached-threshold rates or survival metrics later. |
| Median Current % | Daily excluded, Rolling/Window/Setup/Report pulse historically | Aggregate current progress | Low-Medium | Remove from top summary / Detail | Highly timing-dependent and market-sensitive; can imply precision it does not deserve. | Active %, failure timing, clean active count. |
| Median Max % | Window, Setup Type, Explorer, Top Movers context, Report pulse | Aggregate best excursion | Medium | Secondary / Detail | Some follow-through value, but skewed by fast movers, ADR, and outliers. | Reached +5/+10/+20 rates, failure timing, eligible D3 High as secondary. |
| Eligible Median D3 High % | Daily, Rolling, Window, Setup Type, Report | Early follow-through | Medium | Secondary | Better than raw D3; useful but less direct than survival/failure timing. | Keep secondary; pair with D3 eligible count. |
| Raw D3 High % | Row/detail/audit contexts | Raw follow-through audit | Low for summary, Medium for audit | Detail/Audit Only | Invalid for stopped-before-D3 rows in primary reads; good for raw inspection. | Eligible D3 High for summary. |
| D3 Eligible count | Window Overview | D3 sample context | Medium | Secondary | Good denominator for eligible D3 High, not a primary decision metric. | Keep near eligible D3 High. |
| Median eligible D3 High by trigger/setup | Window/Setup proposed or existing indirectly | Follow-through comparison | Medium | Secondary | Useful after survival quality is known. | Failure timing first, D3 second. |
| Median Current vs Setup Close | Rolling detail | Alternate return reference | Low for summary | Detail/Audit Only | Too technical for top reads. | None. |
| Max Gain from Setup Close | Rolling detail | Alternate return reference | Low for summary | Detail/Audit Only | Useful for audit, not fast decisions. | None. |
| Trigger Rate | Window Overview | Trigger availability/attempt rate | Medium | Secondary | Useful for diagnosing whether setups are firing, but not quality by itself. | Keep in detailed trigger table. |
| Fail % by trigger | Window Overview | Trigger quality | High | Primary | Directly answers whether trigger attempts are failing. | Keep; later split by failure timing. |
| Active after trigger | Window Overview | Trigger survival | High | Primary | Strong quality metric after success. | Keep; add D1-D3 timing. |
| Failed After D0 after trigger | Window Overview | Later failure aggregate | Medium | Replace | Useful but too coarse. | D1/D2/D3/after-D3 failure timing. |
| Most Common Setup / setup frequency | Daily groups, Setup Type Performance context | Frequency/mix | Low-Medium | Secondary / Detail | Frequency is context, not edge; can distract from quality. | Setup success/survival by count-gated setup. |
| Setup Types | Setup Type Performance cards | Coverage/classification context | Medium | Secondary | Useful to assess labeling coverage, not quality. | Keep as context card. |
| Classified Setups | Setup Type Performance cards | Metadata coverage | Medium | Secondary | Useful operationally for data hygiene. | Keep below quality cards. |
| Unclassified Count | Setup Type Performance cards | Metadata hygiene | Medium | Secondary | Useful for cleanup, not performance read. | Keep, but not primary. |
| Highest Active Rate | Setup Type Performance cards | Best setup candidate | Medium-High | Primary with sample gate | Quickly points to what is working, if sample-gated. | Keep; include count/sample. |
| Lowest Failure | Setup Type Performance cards | Best setup candidate | Medium-High | Primary with sample gate | Useful but can overlap with highest active. | Consider merge into "Best Setup Read." |
| Highest Failure | Setup Type Performance cards | Risk setup candidate | High | Primary | Directly flags what is failing. | Keep with sample gate. |
| Failure % | Setup Type Performance | Aggregate setup failure | High | Primary | Clear quality metric, but should later split timing. | Failure timing distribution. |
| Rating Avg | Setup Type Summary | Metadata/context | Low | Detail | Rating is manual and interpretive; average can be mushy. | Rating 4-5 count or filters only. |
| Rating 4-5 Count | Setup Type Summary, Top Movers | Quality/filter context | Medium | Secondary | Useful to understand sample quality; not outcome by itself. | Keep secondary. |
| Entry Tactic metrics | Setup x Entry Tactic | Setup/tactic diagnostics | Medium | Detail/Audit Only | Useful for research, too granular for top summary. | Keep collapsed. |
| Portfolio leaders | Top Movers, Report | Current names to watch | High | Primary on Top Movers/Report | Directly actionable for name review. | Keep. |
| Days Since Setup | Top Movers | Holding age/current-name context | Medium | Secondary/Primary depending view | Useful for Longest Open portfolio view. | Keep in Top Movers. |
| Portfolio eligibility fields | Top Movers audit | Inclusion diagnostics | Medium | Detail/Audit Only | Helps debug why names qualify/exclude. | Keep collapsed. |
| Data freshness fields | Data Health indicators, Top Movers audit | Data quality/freshness | High when stale, Secondary when fresh | Secondary / Alert Primary | Critical if stale; otherwise supporting context. | Keep compact; escalate only on stale/missing data. |
| Market Context | Daily, Rolling, Report | Environmental explanation | High | Primary context | Helps interpret whether outcomes are stock/setup-specific or tape-driven. | Keep as context, not outcome score. |
| RVOL / ATR / range diagnostics | Detail/feature tables | Setup character | Medium for research | Detail/Audit Only | Useful to explain behavior, not top summary. | Keep collapsed/detail. |

## Page-Level Recommendations

### Daily Snapshot

**Keep primary**

- Setups/sample count.
- Active.
- D0 Fail.
- Failed After D0 until failure timing exists.
- Unresolved/untriggered when present.
- Trigger Read success/attempt rates.
- Market Context.

**Demote**

- Close < BE and Retested should remain visible but secondary to active/failure.
- Median eligible D3 High should be secondary, not a core verdict.

**Remove from summary**

- Median Current % and Median Max % should stay out of the Day Read.
- Raw D3 High should stay row/detail only.

**Missing**

- D1/D2/D3/after-D3 failure timing for the selected date when enough triggered rows exist.

### Rolling Backwatch Monitor

**Keep primary**

- Per-date Setups, Active, D0 Fail, Failed After D0.
- Per-date Trigger Read.
- Main row status table.
- Market Context per date.

**Demote**

- Median eligible D3 High should remain secondary follow-through context.
- Close < BE and Retested are useful but secondary.

**Remove from summary**

- Median Current % and Median Max % should not be top-level per-date summary anchors.
- Raw D3 High should remain table/detail only.

**Missing**

- Per-date failure timing distribution could replace the broad Failed After D0 tile later, but only if displayed compactly.

### Window Behavior Overview

**Keep primary**

- Trigger Success % by window.
- Trigger fail rate.
- Active after trigger.
- Sample/attempt count.
- D0 Fail and Failed After D0 at the window level until failure timing exists.
- Trend shifts versus Previous 5.

**Demote**

- Median Max should be secondary in trigger detail tables.
- Median Current should be detail/secondary only.
- Median eligible D3 High should be secondary follow-through context.
- Trigger Rate and Eligible count should support denominator clarity, not headline the page.

**Remove from summary**

- Raw D3 High.
- Large detailed trigger matrices should not be the first read.

**Missing**

- Failure timing by trigger.
- Current Read callouts.
- Trend Shift callouts.
- Biggest improving/degrading trigger with sample gates.

### Trigger Event Explorer

**Keep primary**

- Rows.
- Triggered.
- Success %.
- Active.
- Failed After D0 until failure timing filters exist.
- Median Max as a filter-result context metric, not a quality headline.

**Demote**

- Median Max should remain part of filter context only.
- Current % and Max % should remain sortable row/research fields.

**Remove from summary**

- None urgently; this is a research page where context cards are acceptable.

**Missing**

- Failure timing filter options and summary cards could be useful later: D0, D1-D3, after-D3, active.

### Top Movers

**Keep primary**

- Portfolio leaders.
- Current % and Max % for active/name ranking.
- Rating and days since setup in portfolio context.
- Active table and Top Triggered Watchlist Movers.

**Demote**

- Max % outside ranking contexts.
- D3 High in audit/detail only.

**Remove from summary**

- Trigger/setup performance summaries do not belong here.

**Missing**

- No major summary metric gap. This page should stay name-centric.

### Setup Type Performance

**Keep primary**

- Count/sample.
- Success % or Failure %.
- Active %.
- D0 Fail %.
- Highest Failure.
- Highest Active Rate, with sample gate.
- Setup Success Trend.

**Demote**

- Classified Setups, Setup Types, and Unclassified Count are metadata/context, not performance.
- Median Max and Median Current should be secondary/detail.
- Median eligible D3 High should be secondary.
- Rating Avg should be detail.

**Remove from summary**

- Most Common Setup/frequency-style signals should not be promoted as edge.
- Setup x Entry Tactic should remain collapsed.

**Missing**

- Failure timing by setup.
- Biggest improving/degrading setup type.
- Current Setup Type Read.
- Trend Shift Read.

### Daily Intelligence Report

**Keep primary**

- Latest setup date.
- Setups.
- Active.
- D0 Fail.
- Failed After D0 until failure timing exists.
- Market Context.
- Trigger Read.
- Names to Review.
- Portfolio Snapshot.

**Demote**

- Retested and Close < BE should be supporting early-follow-through context.
- Median eligible D3 High should be included only when meaningful and framed as secondary.

**Remove from summary**

- Median Current and Median Max should not be summary lead items.
- Raw D3 High should not appear.

**Missing**

- Deterministic shift lines: D0 failure rose/fell, trigger improved/degraded, setup type improved/degraded.

### Data Health

**Keep primary only when stale/problematic**

- Data freshness, source coverage, missing/stale status.

**Demote when healthy**

- Data health should be compact when all clear.

**Missing**

- No metric value gap. Its job is trust/freshness, not behavior analysis.

## Recommended Summary Metric Standard

### Single-Day Read

Primary:

- Setups.
- Active.
- D0 Fail.
- Failed After D0, until split timing exists.
- Unresolved/untriggered when nonzero.
- Trigger success/attempt read.
- Market Context.

Secondary:

- Close < BE.
- Retested.
- Eligible Median D3 High.

Detail only:

- Median Current.
- Median Max.
- Raw D3 High.
- Feature diagnostics.

### Rolling Recent Read

Primary:

- Per-date Setups.
- Active.
- D0 Fail.
- Failed After D0.
- Trigger Read.
- Market Context.

Secondary:

- Close < BE.
- Retested.
- Eligible Median D3 High.

Detail only:

- Full raw/audit columns.
- Raw D3 High.
- Alternate return references.

### Window Overview

Primary:

- Current window sample count.
- Trigger Success % with attempts.
- Trigger Fail %.
- Active after trigger.
- D0 Fail and later failure trend.
- Failure timing distribution once added.
- Trend shifts versus Previous 5.

Secondary:

- Eligible Median D3 High.
- Median Max.
- Trigger Rate.
- Eligible count.

Detail only:

- Median Current.
- Raw D3 High.
- Large trigger matrices.
- Opening path diagnostics.

### Setup Type Performance

Primary:

- Setup count/sample.
- Success % or Failure %.
- Active %.
- D0 Fail %.
- Failure timing once added.
- Biggest improving/degrading setup type.
- Highest failure setup.

Secondary:

- Eligible Median D3 High.
- Median Max.
- Rating 4-5 Count.
- Classified/unclassified counts.

Detail only:

- Median Current.
- Rating Avg.
- Setup x Entry Tactic table.

### Trigger Explorer

Primary:

- Filtered rows.
- Triggered count.
- Success %.
- Active count.
- Failed After D0 count, later replaced/supplemented by failure timing.

Secondary:

- Median Max.
- Close < BE if added to cards.

Detail/research:

- Current %.
- Max %.
- Raw D3 High.
- Row-level setup/rating/entry tactic fields.

## Special Review: Median Current, Median Max, Median D3 High

### Median Current %

Recommendation: **Remove from top summary; keep detail/research only.**

Median Current % is strongly dependent on current date, market tape, ticker volatility, and how long a setup has been alive. It can be useful in a filtered research grid or name-ranking context, but it is not a clean summary answer to "is this trigger/setup working?"

Better summary metrics:

- Active %.
- Clean active count.
- Failure timing distribution.
- Trend shift in active/failure rates.

### Median Max %

Recommendation: **Secondary/detail, not primary.**

Median Max % has some follow-through value, but it can be distorted by fast movers, high-ADR names, and outliers. It is more useful in Top Movers, Trigger Event Explorer, and deeper trigger/setup detail than in top summary cards.

Better summary metrics:

- Success %.
- Active %.
- D0/D1/D2/D3/after-D3 failure distribution.
- Reached-threshold rates later, if desired.

### Median D3 High %

Recommendation: **Secondary summary metric using eligible D3 only.**

Eligible D3 High can help interpret early follow-through, especially when comparing otherwise similar trigger/setup groups. It should not outrank survival/failure timing. Raw D3 High should never be used in primary summaries.

Better primary metrics:

- Survived through D3.
- Failed D0/D1/D2/D3.
- Active after D3 or failed after D3.

### Most Common Setup

Recommendation: **Demote to context/detail.**

Frequency helps explain mix, but it does not tell whether the setup has edge. A common setup can be bad, and a rare setup can be excellent but under-sampled.

Better summary metrics:

- Best/worst setup by success/failure rate with sample gates.
- Setup failure timing.
- Setup trend shift.

## Replacement Metrics To Evaluate

### Failure Timing Distribution

For triggered rows:

- D0 Fail %.
- D1 Fail %.
- D2 Fail %.
- D3 Fail %.
- Failed After D3 %.
- Active %.

Use as primary in Window Overview and Setup Type Performance. Use as compact secondary in Daily Snapshot/Rolling if screen space allows.

### Trigger Survival

For each trigger:

- Attempts.
- Success %.
- Active %.
- D0 Fail %.
- D1-D3 Fail %.
- Failed After D3 %.
- Eligible Median D3 High as secondary.

Recommended page: Window Behavior Overview.

### Setup Survival

For each setup:

- Count.
- Success %.
- Active %.
- D0 Fail %.
- D1-D3 Fail %.
- Failed After D3 %.
- Eligible Median D3 High as secondary.

Recommended page: Setup Type Performance.

### Trend Shift Callouts

Recommended deterministic callouts:

- "VWAP Reclaim improved from 60% to 85% success, 8 vs 12 attempts."
- "1m ORH deteriorated from 70% to 40% success, 10 vs 9 attempts."
- "D0 Fail rose from 10% to 25%."
- "Failed After D0 rose, suggesting more late breakdowns."

Do not speculate on causes. Use market context as adjacent context, not proof.

## Recommended Next Implementation Chunks

### 1. Add Failure Timing Distribution Helper

- **Why it matters:** Replaces fuzzy broad metrics with the clearest survival/risk breakdown.
- **Files likely involved:** New `src/failure_timing.py` or helpers in `src/setup_behavior_overview.py` and `src/setup_performance.py`; tests.
- **Complexity:** Medium.
- **Risk:** Low-medium if additive and based on existing `Trigger Day` and `Current Status`.
- **Tests needed:** D0 trigger fail, Failed D0, Failed D1, Failed D2, Failed D3, Failed D4+, Active, Unresolved, denominator behavior, group-by trigger/setup/window.

### 2. Demote Median Current / Median Max / Median D3 In Top Summary Views

- **Why it matters:** Reduces fuzziness and prevents volatile names from shaping the top read.
- **Files likely involved:** `pages/5_Window_Behavior_Overview.py`, `pages/8_Setup_Type_Performance.py`, `src/setup_behavior_overview.py`, `src/setup_performance.py`, `src/daily_report.py`.
- **Complexity:** Low-medium.
- **Risk:** Low if layout-only; medium if tests assert table columns.
- **Tests needed:** Page/table rendering expectations, summary metric presence/absence tests, eligible D3 remains available where intended.

### 3. Add Current Read / Trend Shift Callouts

- **Why it matters:** Gives deterministic 5-second interpretation before dense tables.
- **Files likely involved:** `src/setup_behavior_overview.py`, `src/setup_performance.py`, `src/daily_report.py`, relevant pages.
- **Complexity:** Medium.
- **Risk:** Low if using existing metrics and sample gates.
- **Tests needed:** Biggest improving/degrading trigger/setup, rising D0 fail, rising later fail, insufficient sample suppression, exact text/evidence values.

### 4. Simplify Window Behavior Overview Summary Hierarchy

- **Why it matters:** This page has the most overlap and would benefit most from fewer visible tables.
- **Files likely involved:** `pages/5_Window_Behavior_Overview.py`, possibly no calculation files.
- **Complexity:** Low-medium.
- **Risk:** Low.
- **Tests needed:** Page source heading/collapse expectations if covered; no calculation tests unless metrics change.

### 5. Simplify Setup Type Performance Summary Metrics

- **Why it matters:** Makes setup quality easier to read and separates metadata coverage from performance.
- **Files likely involved:** `pages/8_Setup_Type_Performance.py`, `src/setup_performance.py`.
- **Complexity:** Medium.
- **Risk:** Low-medium.
- **Tests needed:** Setup cards, setup trend, setup summary column behavior, sample gates, failure timing once added.

## Validation Notes

This audit added documentation only. No tests were required or run.
