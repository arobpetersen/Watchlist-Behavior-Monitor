# Watchlist Behavior Monitor Metrics System Audit

Date: 2026-05-21

Scope: audit only. No calculation, lifecycle, trigger/status, market-context, table-definition, UI, page-render data-fetch, or LLM integration changes are proposed as implemented work in this document.

## Executive Summary

The app has strong raw material: daily operational reads, recent-window comparisons, trigger-event research, setup-type performance, active/progressing names, and a short written report. The current issue is not missing sophistication. The issue is that several pages now answer adjacent questions with overlapping tables, so the user's first read can be slower than it needs to be.

The clearest next product direction is to separate page jobs more sharply:

- **Daily Snapshot and Rolling Backwatch Monitor** should stay operational: what happened on one date or the most recent few dates.
- **Window Behavior Overview** should become the main trigger/window trend page: current window read, trend shift read, trigger success trend, failure timing by trigger, then collapsed historical detail.
- **Setup Type Performance** should become the setup-quality page: current setup read, setup trend shift, failure timing by setup, setup summary, then collapsed setup x entry tactic detail.
- **Trigger Event Explorer** should own row-level research and export. It should not need to duplicate high-level summaries from overview pages.
- **Top Movers** should own active/progressing names and portfolio review, not trigger or setup quality.
- **Daily Intelligence Report** should be a short synthesis of current state plus material shifts, not another dense metrics page.

The biggest missing simple metric is **failure timing distribution**: of triggered setups, what percent failed D0, D1, D2, D3, after D3, and what percent remain active. This would answer a core trading question more directly than several existing broad tables.

## Current Product Questions

The metrics system should make these questions explicit:

- **Current state:** What is working right now? Which triggers/setup types are clean? Which names are active and progressing? What is failing now?
- **Trend shift:** What changed versus the prior window? Are VWAP Reclaims, 1m ORH, 5m ORH, D0 failures, later failures, and early follow-through improving or deteriorating?
- **Failure timing:** Among triggered setups, where are they stopping out: D0, D1, D2, D3, after D3, or still active?
- **Trigger quality:** For each trigger, what are attempts, success rate, D0 fail rate, survival, active after trigger, later failure rate, and eligible D3 High?
- **Setup type quality:** For each setup type, what are count, active rate, D0/later failure profile, eligible D3 High, and trend direction?

## Page Purpose Map

### Daily Snapshot

**Intended job:** Give a single setup date's operational read and editable candidate list.

- **Primary user question:** What happened on this setup date?
- **First 10-second read:** Market Context, Day Read, Trigger Read.
- **Secondary/audit detail:** Setup Candidates, Edit Selected Candidate, Daily Feature Detail, Group Summaries.
- **Current supporting metrics/tables:** Market context strip, Day Read tiles, Trigger Read tiles, setup candidate table, rating/setup/focus group summaries.
- **Potential distractions:** Group Summaries may overlap with Setup Type Performance and may be too low-value on a single-date operational page unless used for quick metadata QA.
- **Recommended stance:** Keep as single-date current state. Do not turn it into a trend page.

### Rolling Backwatch Monitor

**Intended job:** Review the latest few setup dates using canonical trigger/status rows.

- **Primary user question:** Across recent dates, which rows are active, failed, or need review?
- **First 10-second read:** Per-date Market Context, Day Read, Trigger Read.
- **Secondary/audit detail:** Main monitor row table, edit manual fields, full detail table, OR Trigger audit.
- **Current supporting metrics/tables:** Per-date summary, trigger read strip, main monitor table, full detail table.
- **Potential distractions:** Repeats Daily Snapshot's Day Read/Trigger Read for each date; that is useful operationally but should not become the app's trend analysis surface.
- **Recommended stance:** Keep as recent-date operational review. Use it to inspect rows, not to explain broad trend shifts.

### Window Behavior Overview

**Intended job:** Compare recent back-watch windows and surface what is improving or degrading.

- **Primary user question:** What changed across recent windows, especially for triggers and broad outcome quality?
- **First 10-second read:** Current Window Read plus Trend Shift Read.
- **Secondary/audit detail:** Trigger Success Trend, failure timing by trigger, historical trigger outcomes, selected-window row preview.
- **Current supporting metrics/tables:** Historical Window Summary, Daily Intelligence Report expander, Selected Window Snapshot, Selected Window Successful Triggers, Trigger Success Trend, Trigger Event Outcomes Across Windows, Supporting Selected-Window Stats.
- **Potential distractions:** Selected Window Successful Triggers, Trigger Success Trend, Trigger Event Outcomes Across Windows, Opening Path Detail, Trigger Event Detail, and Primary/Final Trigger Outcome all touch similar trigger-quality territory with different denominators.
- **Recommended stance:** Make this the main trend-shift page, but reduce trigger table sprawl by promoting one current-read summary and one trend-shift summary.

### Trigger Event Explorer

**Intended job:** Filter/export row-level trigger outcomes for deeper research.

- **Primary user question:** Which rows match a specific trigger/status/setup/rating/filter condition?
- **First 10-second read:** Active filter summary, summary cards, filtered row count.
- **Secondary/audit detail:** Filtered row grid and CSV export.
- **Current supporting metrics/tables:** Filter controls, summary cards, filtered results table.
- **Potential distractions:** Low. This page is already positioned as research/detail.
- **Recommended stance:** Keep granular. Move deeper row-level/audit needs here instead of adding them to overview pages.

### Top Movers

**Intended job:** Identify active/progressing names and review portfolio-style candidates.

- **Primary user question:** Which watchlist names are active, fresh, progressing, or leading?
- **First 10-second read:** Hypothetical Portfolio View and Top 10 Active Watchlist Movers.
- **Secondary/audit detail:** Portfolio Eligibility Audit, Top Triggered Watchlist Movers, Details/Audit.
- **Current supporting metrics/tables:** Portfolio table, eligibility funnel, active movers, triggered movers, audit table.
- **Potential distractions:** Top Triggered Watchlist Movers can resemble performance/ranking research, but it is still name-centric rather than trigger/setup quality-centric.
- **Recommended stance:** Keep as current-name and portfolio review. Avoid adding trigger/setup trend summaries here.

### Setup Type Performance

**Intended job:** Evaluate manually logged setup types and whether their outcomes are improving or deteriorating.

- **Primary user question:** Which setup types are working, failing, or changing?
- **First 10-second read:** Setup performance cards plus Setup Success Trend.
- **Secondary/audit detail:** Setup Summary, Setup x Entry Tactic.
- **Current supporting metrics/tables:** Classified setup cards, Setup Success Trend, Setup Summary, Setup x Entry Tactic.
- **Potential distractions:** Setup Summary is wide; Setup x Entry Tactic is appropriately collapsed but can overlap with Setup Summary.
- **Recommended stance:** Add clearer Current Read and Trend Shift sections later, then add setup failure timing. Keep Setup Summary as the main detail table.

### Daily Intelligence Report

**Intended job:** Provide a short written synthesis of the latest current read and material shifts.

- **Primary user question:** What should I know from the latest behavior without scanning every table?
- **First 10-second read:** Summary Read.
- **Secondary/audit detail:** Day Read, Trigger Read, Names to Review, Portfolio Snapshot.
- **Current supporting metrics/tables:** Summary bullets, Market Context, Day Read table, Trigger Read table, Names to Review, Portfolio Snapshot.
- **Potential distractions:** If expanded inside Window Behavior Overview, it competes with the overview's own current/trend sections.
- **Recommended stance:** Keep short. Use it as synopsis only: current state plus deterministic shifts.

## Metric And Table Inventory

| Page | Section/table | Measures | Type | Overlap | Value | Later action |
|---|---|---|---|---|---|---|
| Daily Snapshot | Market Context | Proxy move, day type, gap, close position, range | Current-state context | Rolling per-date market context | High | Stay |
| Daily Snapshot | Day Read | Setups, Active, D0 Fail, Failed After D0, Close < BE, Retested, Median eligible D3 High | Current state | Rolling per-date Day Read, Daily Report Day Read | High | Stay |
| Daily Snapshot | Trigger Read | Per-trigger success/fail attempt read for one date | Current state | Rolling Trigger Read, Daily Report Trigger Read | High | Stay |
| Daily Snapshot | Setup Candidates | Row-level candidate status and metrics | Audit/detail | Rolling main table, Explorer rows | High | Stay |
| Daily Snapshot | Daily Feature Detail | Entry-day feature diagnostics | Audit/detail | Low overlap | Medium | Keep collapsed |
| Daily Snapshot | Group Summaries | Rating/setup/focus aggregation for one day | Current-state grouping | Setup Type Performance | Medium | Consider collapse or rename as single-date grouping |
| Rolling Backwatch Monitor | Per-date Market Context | Market context by setup date | Current state | Daily Snapshot | High | Stay |
| Rolling Backwatch Monitor | Per-date Day Read | Same day-read metrics across recent dates | Current state | Daily Snapshot, Daily Report | High | Stay |
| Rolling Backwatch Monitor | Trigger Read Strip | Per-date trigger read | Current state | Daily Snapshot, Daily Report | High | Stay |
| Rolling Backwatch Monitor | Main table | Canonical row status/trigger/returns | Audit/detail | Daily Snapshot rows, Explorer rows | High | Stay |
| Rolling Backwatch Monitor | Full detail table | Raw/audit columns and diagnostics | Audit/detail | Explorer rows, OR audit | Medium | Keep collapsed; consider moving more detail to Explorer later |
| Rolling Backwatch Monitor | Audit OR Trigger | Candidate-specific OR trigger diagnostics | Audit/detail | Trigger Event Explorer partially | High for debugging | Keep collapsed |
| Window Behavior Overview | Historical Window Summary | Window-level rates and medians | Trend/current comparison | Daily Report pulse, selected snapshot | Medium | Simplify or keep as compact comparison |
| Window Behavior Overview | Daily Intelligence Report expander | Written latest read and trigger/name synopsis | Synthesis | Daily Report content | High | Keep collapsed or move to report-only page if standalone exists |
| Window Behavior Overview | Selected Window Snapshot | Current selected-window cards/read | Current-state window | Historical summary | High | Promote as Current Window Read |
| Window Behavior Overview | Selected Window Successful Triggers | Successful trigger rows: count, active, failed after D0, median max | Current-state trigger quality | Trigger Event Outcomes, Trigger Success Trend | Medium | Merge into Current Trigger Read or collapse |
| Window Behavior Overview | Trigger Success Trend | Success percent by trigger across windows | Trend | Trigger Event Outcomes Across Windows | High | Stay, but pair with deterministic shift callouts |
| Window Behavior Overview | Trigger Event Outcomes Across Windows | Eligible, triggered, failed, success, active, failed after D0, median max by trigger/window | Trend/research-grid | Trigger Success Trend, Selected Window Successful Triggers | High but dense | Collapse after current/trend summaries |
| Window Behavior Overview | Opening Path Detail | Opening path groups and outcome medians | Audit/detail | Selected Window Successful Triggers | Medium | Keep collapsed |
| Window Behavior Overview | Trigger Event Detail | Full per-trigger/window comparison table | Research-grid | Trigger Event Outcomes Across Windows | Medium | Move/collapse; likely Explorer-adjacent |
| Window Behavior Overview | Selected Window Breakdown | Metric cards by trigger-day/current/mix/diagnostics | Current-state detail | Selected Window Snapshot | Medium | Keep collapsed |
| Window Behavior Overview | Selected Window Mix | Trigger/setup/rating mix | Current-state detail | Daily Snapshot Group Summaries, Setup Performance | Medium | Keep collapsed |
| Window Behavior Overview | Primary/Final Trigger Outcome | Final trigger label quality | Current-state/research | Trigger Event Outcomes | Medium | Keep collapsed or merge with trigger current read |
| Window Behavior Overview | Selected Window Ticker Detail Preview | First rows from detail grid | Audit preview | Trigger Event Explorer | Low-medium | Keep collapsed; direct users to Explorer |
| Trigger Event Explorer | Summary cards | Rows, triggered, success %, active, failed after D0, median max | Research-grid summary | Window trigger summaries | Medium | Stay as filter context |
| Trigger Event Explorer | Filtered results | Row-level trigger/setup/status data | Research-grid | Rolling detail, Window preview | High | Stay |
| Top Movers | Hypothetical Portfolio View | Active 4-5 star qualifying portfolio rows | Current-state names | Daily Report portfolio snapshot | High | Stay |
| Top Movers | Portfolio Eligibility Audit | Inclusion/exclusion funnel and samples | Audit/detail | None significant | Medium | Keep collapsed |
| Top Movers | Top 10 Active Watchlist Movers | Active names by Current %, rating, max | Current-state names | Daily Report Names/Portfolio | High | Stay |
| Top Movers | Top Triggered Watchlist Movers | Ranked triggered rows by max/current/days | Research-grid | Trigger Event Explorer row sorting | Medium | Stay as reference; avoid expanding |
| Top Movers | Details/Audit | Entry refs, exclusion reasons, raw return references | Audit/detail | Rolling detail | Medium | Keep collapsed |
| Setup Type Performance | Setup performance cards | Classified counts, setup types, high/low active/failure | Current-state setup quality | Setup Summary | High | Stay, but sharpen into Current Setup Type Read |
| Setup Type Performance | Setup Success Trend | Success percent by setup across windows | Trend | Setup Summary | High | Stay |
| Setup Type Performance | Setup Summary | Count, active, D0 fail, failed after D0, close BE, retests, current/max/D3, rating | Current-state/detail | Cards, trend, Daily Snapshot group summaries | High but wide | Stay as main detail; consider column groups later |
| Setup Type Performance | Setup x Entry Tactic | Setup/tactic counts and outcome rates | Research-grid | Setup Summary | Medium | Keep collapsed |
| Daily Intelligence Report | Summary Read | Latest date, market context, trigger read, follow-through bullets | Synthesis | Daily Snapshot, Window Overview | High | Stay concise |
| Daily Intelligence Report | Day Read | Latest day-read table | Current state | Daily Snapshot | High | Stay |
| Daily Intelligence Report | Trigger Read | Latest trigger read | Current state | Daily Snapshot/Rolling | Medium | Stay short |
| Daily Intelligence Report | Names to Review | Notable tickers and reasons | Current-state names | Top Movers | High | Stay |
| Daily Intelligence Report | Portfolio Snapshot | Current Progress portfolio line | Current-state names | Top Movers | High | Stay |

## Overlap Findings

### Trigger Success Trend vs Trigger Event Outcomes Across Windows

Both answer trigger quality across windows. Trigger Success Trend is a compact trend view. Trigger Event Outcomes Across Windows is a detailed matrix with eligibility, trigger rate, fail rate, success rate, active rate, later failure rate, and median max.

Recommendation: keep Trigger Success Trend as the promoted table, then collapse Trigger Event Outcomes as supporting evidence.

### Selected Window Successful Triggers vs Primary/Final Trigger Outcome

Both summarize trigger quality for a selected window, but one is based on successful displayed triggers and the other is based on final/primary trigger label.

Recommendation: later merge into one Current Trigger Read with clear denominators, then keep the other as audit/detail if still needed.

### Daily Snapshot Trigger Read, Rolling Trigger Read, Daily Report Trigger Read

These intentionally repeat the same concept at different scopes: selected date, recent per-date review, written latest-date report.

Recommendation: keep all three, but avoid adding more trigger summaries to these pages.

### Setup Success Trend vs Setup Summary

Setup Success Trend is a compact trend table. Setup Summary is a wide current/detail table.

Recommendation: keep both, but add a short Current Setup Type Read and Trend Shift Read above them so users do not need to scan both tables immediately.

### Trigger Event Explorer Rows vs Rolling/Window Detail Tables

Explorer is the best home for granular research and export. Rolling and Window detail tables are useful previews but can clutter overview pages.

Recommendation: keep Rolling detail because it is operational. Keep Window detail preview collapsed and continue pointing users to Explorer.

## Current-State Vs Trend-Shift Clarity

| Page | Current Read section? | Trend Shift section? | Deeper Detail/Audit section? | Notes |
|---|---:|---:|---:|---|
| Daily Snapshot | Yes | No | Yes | Single-date page; do not add trend shift. |
| Rolling Backwatch Monitor | Yes, per date | No | Yes | Recent operational review; trend belongs elsewhere. |
| Window Behavior Overview | Yes, should be promoted | Yes, should be explicit | Yes | Best candidate for deterministic current/shift callouts. |
| Trigger Event Explorer | Filter context only | No | Yes | Research page; trend callouts would distract. |
| Top Movers | Yes | No or minimal | Yes | Name/portfolio current state; avoid trigger/setup trend duplication. |
| Setup Type Performance | Yes, should be promoted | Yes, should be explicit | Yes | Needs setup-specific current/shift callouts. |
| Daily Intelligence Report | Yes | Yes, concise | No heavy detail | Written synopsis only. |

Recommended deterministic language style:

- "Current read: VWAP Reclaim has the highest recent trigger success rate among triggers with at least N attempts."
- "Shift: 1m ORH success decreased from X to Y versus Previous 5."
- "D0 failures increased from X to Y in Last 5 versus Previous 5."
- "Setup type Pullback improved from X to Y success in Last 5 versus Previous 5."

Do not generate speculative explanation. Each line should cite the metric, window, prior value, current value, and sample count.

## Missing Simple Metrics

### 1. Failure Timing Distribution

This is the highest-value missing simple metric.

For triggered setups, expose:

- D0 Fail %
- D1 Fail %
- D2 Fail %
- D3 Fail %
- Failed After D3 %
- Active %
- Unresolved %, if included in denominator

Suggested denominator choices:

- **Triggered denominator:** `Trigger Day in {Success, Fail}`. This best answers "of triggered stocks, what stopped out when?"
- **All setup denominator:** optional separate context row, but not primary for failure timing.
- **Unresolved:** show separately as context, not part of triggered survival unless the table title says "all setups."

Feasible from existing data:

- `Trigger Day == Fail` maps to D0 fail.
- `Current Status == Failed D0/D1/D2/D3/D4+` maps to failure timing.
- `Current Status == Active` maps to active.
- `Trigger Day == Unresolved` maps to unresolved/no trigger.

No lifecycle changes are needed to compute this later.

### 2. Trigger Survival Table

Potential table: `Trigger Survival by Window`.

Rows: Trigger.

Columns:

- Attempts
- D0 Fail %
- D1 Fail %
- D2 Fail %
- D3 Fail %
- After D3 Fail %
- Active %
- Success %

Better design than all windows in one giant table:

- Use a selected window control and show one compact table for that window.
- Add a small "Last 5 vs Previous 5" shift table or callouts above it.
- Keep Last 10/Last 20 available in a window selector rather than as repeated wide columns.

This avoids a matrix that becomes too wide and hard to scan.

### 3. Setup Survival Table

Same concept grouped by Setup type:

- Setup
- Count/Attempts
- D0 Fail %
- D1 Fail %
- D2 Fail %
- D3 Fail %
- After D3 Fail %
- Active %
- Median eligible D3 High

Recommended location: Setup Type Performance, below Setup Success Trend and above Setup Summary.

### 4. Trend-Shift Callouts

Useful deterministic callouts:

- Biggest improving trigger by success rate, gated by minimum attempts.
- Biggest degrading trigger by success rate, gated by minimum attempts.
- Biggest improving setup type by success rate, gated by minimum count.
- Biggest degrading setup type by success rate, gated by minimum count.
- Rising D0 failures.
- Rising Failed After D0.
- Improving/worsening eligible D3 High, only when enough eligible D3 rows exist.

These should be deterministic summaries of existing tables, not generated commentary.

### 5. Eligible D3 High Clarity

Eligible D3 High belongs in primary summary contexts where follow-through quality is being compared:

- Daily Snapshot Day Read
- Rolling Backwatch Monitor Day Read
- Window Behavior Overview Current Outcome / trend
- Setup Type Performance summary
- Daily Intelligence Report Day Read

Raw D3 High belongs in detail/audit contexts:

- Rolling detail table
- Trigger Event Explorer row grid if useful
- Top Movers audit
- Any row-level diagnostics

Avoid showing raw and eligible D3 side by side in top-level summary pages unless the page is explicitly an audit page.

## Simplification Opportunities

### Window Behavior Overview

Potential final shape:

1. Current Window Read
2. Trend Shift Read
3. Trigger Success Trend
4. Failure Timing by Trigger
5. Historical Trigger Outcomes collapsed
6. Supporting selected-window stats collapsed
7. Row preview collapsed with link/caption to Trigger Event Explorer

Recommended simplifications:

- Promote Selected Window Snapshot into Current Window Read.
- Add Trend Shift Read above tables.
- Keep Trigger Success Trend visible.
- Add Failure Timing by Trigger later as a high-value simple table.
- Collapse Trigger Event Outcomes Across Windows by default after the trend table.
- Merge or collapse Selected Window Successful Triggers and Primary/Final Trigger Outcome because they compete as "current trigger quality" tables.
- Keep Opening Path Detail and Trigger Event Detail collapsed.

### Setup Type Performance

Potential final shape:

1. Current Setup Type Read
2. Setup Trend Shift Read
3. Setup Success Trend
4. Failure Timing by Setup
5. Setup Summary
6. Setup x Entry Tactic collapsed

Recommended simplifications:

- Convert cards into clearer Current Setup Type Read.
- Add deterministic improving/worsening setup callouts.
- Add failure timing by setup before the wide summary table.
- Keep Setup x Entry Tactic collapsed.
- Consider grouping Setup Summary columns later: sample/count, outcome, follow-through, metadata.

### Daily Snapshot

Recommended simplifications:

- Keep top panel as-is: market, day read, trigger read.
- Keep candidate table central.
- Keep Daily Feature Detail collapsed.
- Consider collapsing Group Summaries by default or moving deeper setup-quality interpretation to Setup Type Performance.

### Rolling Backwatch Monitor

Recommended simplifications:

- Keep per-date operational layout.
- Keep full detail collapsed.
- Avoid adding trend tables here.
- Update D3 definition text later to match eligible/raw distinction.

### Trigger Event Explorer

Recommended simplifications:

- Keep filters and export central.
- Consider adding optional failure-day filters later, but only after shared failure timing helpers exist.
- Do not add heavy trend summaries here.

### Top Movers

Recommended simplifications:

- Keep portfolio and active movers prominent.
- Keep eligibility audit collapsed.
- Avoid adding setup/trigger trend tables.
- Consider keeping Top Triggered Watchlist Movers as reference rather than a primary read.

### Daily Intelligence Report

Recommended simplifications:

- Keep Summary Read short.
- Include only the most important deterministic current and shift statements.
- Avoid adding all tables from Window Behavior Overview.

## Proposed Simplified Metrics Hierarchy

### Daily Snapshot

- Market Context
- Day Read
- Trigger Read
- Setup Candidates
- Detail/feature/group tables collapsed

### Rolling Backwatch Monitor

- Per-date Market Context
- Per-date Day Read
- Per-date Trigger Read
- Main monitor rows
- Edit/manual fields
- Full detail and OR audit collapsed

### Window Behavior Overview

- Current Window Read
- Trend Shift Read
- Trigger Success Trend
- Failure Timing by Trigger
- Historical Trigger Outcomes collapsed
- Supporting selected-window stats collapsed
- Ticker detail preview collapsed

### Trigger Event Explorer

- Filters
- Summary cards for active filters
- Granular rows
- CSV export

### Top Movers

- Portfolio View
- Top Active Watchlist Movers
- Top Triggered Watchlist Movers
- Eligibility/audit collapsed

### Setup Type Performance

- Current Setup Type Read
- Setup Trend Shift Read
- Setup Success Trend
- Failure Timing by Setup
- Setup Summary
- Setup x Entry Tactic collapsed

### Daily Intelligence Report

- Summary Read
- Market Context
- Day Read
- Trigger Read
- Names to Review
- Portfolio Snapshot

## Recommended Implementation Chunks

### 1. Add Shared Failure Timing Helpers

- **What it changes:** Add pure helper functions that classify rows into D0, D1, D2, D3, after D3, active, unresolved, and produce grouped distributions by window/trigger/setup.
- **Why it matters:** Directly answers the user's most important missing question: "What percentage stopped out on D0, D1, D2, D3?"
- **Files likely involved:** `src/setup_behavior_overview.py`, possibly new `src/failure_timing.py`, `src/setup_performance.py`, tests.
- **Complexity:** Medium.
- **Risk:** Low-medium, if implemented as additive helpers with no lifecycle changes.
- **Tests needed:** Unit tests for classification, triggered denominator, D0 trigger fail, Failed D1/D2/D3/D4+, Active, Unresolved, grouped medians/counts.

### 2. Add Current Read / Trend Shift Callouts To Window Behavior Overview

- **What it changes:** Add deterministic current-window and Last 5 vs Previous 5 callouts above existing tables.
- **Why it matters:** Highest clarity improvement without removing any data.
- **Files likely involved:** `src/setup_behavior_overview.py`, `pages/5_Window_Behavior_Overview.py`, tests.
- **Complexity:** Medium.
- **Risk:** Low, if callouts are derived from existing tables.
- **Tests needed:** Deterministic callout selection, sample gates, no speculative text, no callout when sample is insufficient.

### 3. Simplify Window Behavior Overview Table Hierarchy

- **What it changes:** Keep Trigger Success Trend visible; collapse or merge overlapping trigger detail tables; move row/detail emphasis toward Trigger Event Explorer.
- **Why it matters:** Reduces density on the page with the most overlap.
- **Files likely involved:** `pages/5_Window_Behavior_Overview.py`, possibly no calculation files.
- **Complexity:** Low-medium.
- **Risk:** Low if only layout/collapse changes.
- **Tests needed:** Page source/layout tests if existing tests assert headings; no data-calculation tests unless helpers change.

### 4. Add Setup Type Current/Trend Read And Failure Timing

- **What it changes:** Add setup-specific current read, deterministic improving/worsening setup callouts, and failure timing by setup.
- **Why it matters:** Makes Setup Type Performance answer setup quality directly instead of forcing the user to scan wide tables.
- **Files likely involved:** `src/setup_performance.py`, `pages/8_Setup_Type_Performance.py`, tests.
- **Complexity:** Medium.
- **Risk:** Low-medium.
- **Tests needed:** Setup trend callout selection, setup failure timing grouping, small sample behavior, eligible D3 High handling.

### 5. Align Daily Intelligence Report With Current + Shift Synopsis

- **What it changes:** Keep the report short but add deterministic shift lines from shared trend helpers once those exist.
- **Why it matters:** Gives the user a fast written read without adding another dense page.
- **Files likely involved:** `src/daily_report.py`, `pages/5_Window_Behavior_Overview.py` if report stays embedded, tests.
- **Complexity:** Medium.
- **Risk:** Low if using existing/additive helpers.
- **Tests needed:** Markdown output tests for current state, shift inclusion, omission on insufficient sample, no speculative language.

## Suggested Priority Order

1. Add Shared Failure Timing Helpers.
2. Add Current Read / Trend Shift Callouts to Window Behavior Overview.
3. Add Failure Timing by Trigger to Window Behavior Overview.
4. Add Setup Type Current/Trend Read and Failure Timing by Setup.
5. Collapse/merge redundant Window Behavior Overview tables after the new reads are trusted.

This order prioritizes direct decision value, low calculation risk, and minimal UI disruption.

## Validation Notes

This audit added documentation only. No tests were required or run for this documentation-only change.
