# Watchlist Behavior Monitor Performance Audit

Date: 2026-05-14

## Executive Summary

The app's main performance constraint is still the canonical full-history build:
`monitor_history()` rebuilds Rolling Setup Monitor rows for every setup date and took about
16.0 seconds for the current local database.

The expensive work is not DuckDB query time. The slow path is mostly Python-side row
derivation inside `rolling_setup_monitor()` plus a second VWAP/display-trigger pass inside
`monitor_history()`.

Setup Performance is healthy after the recent cache-token fix. Its aggregation took about
0.06 seconds once shared monitor history already existed.

The most important newly confirmed issue is Data Health. On a cold cache,
`build_data_health_summary()` calls `active_daily_bar_coverage()`, which calls full
`monitor_history()` when no history is passed. That makes the small Data Health indicator
capable of taking about 16.2 seconds on cache miss.

Update: the first narrow fix replaced the default Data Health active-coverage source with a
fast watchlist-candidate daily-bar coverage check. Passing precomputed monitor history still
uses exact canonical active rows. The uncached local timing after the fix is about 0.21
seconds.

## Current Data Size

Measured against:

`data/db/watchlist.duckdb`

| Item | Count |
| --- | ---: |
| `watchlist_candidates` | 115 |
| Distinct setup dates | 23 |
| `daily_bars` | 4,020 |
| `intraday_bars_1m` | 78,328 |
| `behavior_labels` | 115 |
| `entry_day_features` | 115 |
| Average tickers per setup date | 5.00 |
| Max tickers per setup date | 11 |

## Measured Timings

Representative local timings from direct helper calls:

| Workflow / Helper | Time |
| --- | ---: |
| Daily Snapshot selected-date monitor table, 2026-05-13 | 0.57s |
| Daily Snapshot supporting metrics/tables/context | ~0.05s total |
| Rolling Setup Monitor, latest 5 setup dates | 2.56s |
| Full `monitor_history()`, all 23 setup dates | 16.01-16.14s |
| Setup Behavior Overview using existing history | 0.86-0.87s |
| Setup Performance filter + summary + tactic summary + cards | ~0.06s |
| Top Movers load using existing history | 0.01s |
| Top Movers row mapping | 0.10s |
| Top Movers table build from mapped rows | 0.16s |
| Daily Intelligence Report payload using existing history/overview | 1.03s |
| Daily Intelligence Report markdown/prompt rendering | ~0.00s |
| Data Health summary, uncached | 16.18s |

## Slowest Functions

Full `monitor_history()` timing detail:

| Step | Time |
| --- | ---: |
| `monitor_history rolling sections build` | 14.02s |
| `Rolling Setup Monitor derivation: retests/follow-through` | 3.17s |
| `Rolling Setup Monitor derivation: ORH/PDH triggers` | 2.82s |
| `Rolling Setup Monitor derivation: bar slicing` | 2.80s |
| `Rolling Setup Monitor derivation: trigger resolution` | 2.41s |
| `monitor_history VWAP/display trigger pass` | 2.03s |
| `monitor_history derivation: raw VWAP reclaim` | 1.96s |
| `Rolling Setup Monitor derivation: VWAP reclaim` | 1.93s |
| `Rolling Setup Monitor dataframe formatting` | 0.78s |

The SQL reads were small by comparison:

| SQL Step | Time |
| --- | ---: |
| Rolling candidates/features | 0.01s |
| Rolling daily bars | 0.01s |
| Rolling intraday bars | 0.05s |
| VWAP intraday bars | 0.03s |

## Page / Workflow Notes

### Daily Snapshot

Current path is selected-date only and reasonably fast. The selected date measured at about
0.57 seconds for 6 rows. Market context and summary/group tables are cheap.

Potential issue: the selected-date workflow table is not currently behind a Streamlit
`st.cache_data` page loader, so ordinary reruns recompute the selected date.

### Rolling Setup Monitor

Latest 5 setup dates measured at about 2.56 seconds for 26 rows. This page uses its own
cached loader:

`load_rolling_setup_sections(db_path, rolling_cache_token)`

Token:

`rolling-monitor-vwap-triggered-fail-v1:{data_health_cache_token(db_path)}`

This avoids building all dates for the Rolling page, but it does not reuse full shared
monitor history if another page already built it.

### Setup Behavior Overview

This page uses the shared full-history loader:

`load_cached_monitor_history(db_path, monitor_history_cache_token)`

Token:

`monitor-history-vwap-triggered-fail-v1:{data_health_cache_token(db_path)}`

The overview transformation itself is under 1 second after history exists. The cold path is
dominated by shared `monitor_history()`.

Daily Intelligence Report is rendered inside this page. Payload assembly measured about
1.03 seconds after history and overview existed; markdown and prompt rendering were
effectively free.

### Watchlist Top Movers

This page uses the same shared full-history loader/token as Setup Behavior Overview and
Setup Performance. After history exists, Top Movers is cheap:

- source load: about 0.01s
- row mapping: about 0.10s
- active/portfolio table build: about 0.16s

### Setup Performance

This page now correctly uses:

`load_cached_monitor_history(db_path, history_cache_token)`

with:

`monitor-history-vwap-triggered-fail-v1:{data_health_cache_token(db_path)}`

Aggregation is not the bottleneck. It measured about 0.06 seconds after shared monitor
history existed.

### Data Health Indicator

This is the highest-priority surprise.

`load_data_health_summary()` is cached, but on cache miss it calls:

`build_data_health_summary()` -> `active_daily_bar_coverage()` -> `monitor_history(con)`

That means a tiny header diagnostic can trigger a full 16 second canonical history rebuild.
The indicator appears on Setup Behavior Overview, Watchlist Top Movers, and Setup
Performance.

### Daily Pipeline / Ingest / Compute

`run_daily_pipeline()` keeps API fetches out of page render, which is good.

The pipeline still works row-by-row:

- one intraday existence check/fetch per candidate
- one daily fetch window per ticker/setup-date pair
- one QQQ daily fetch window per setup date
- one `compute_features()` pass per candidate
- one behavior-label assignment per setup date

This is acceptable outside page render, but it is a likely future pipeline bottleneck as
candidate count grows.

## Cache Design Findings

### Shared Full Monitor History

Shared cache function:

`src/monitor_history_loader.py::load_cached_monitor_history(db_path, cache_version)`

Used by:

- Setup Behavior Overview
- Watchlist Top Movers
- Setup Performance

The recent Setup Performance cache-token fix is confirmed.

### Cache Token Inputs

`data_health_cache_token(db_path)` includes:

- DuckDB file mtime
- DuckDB file size
- `watchlist_candidates` fingerprint using count, max candidate id, setup, entry tactic,
  rating, date, and ticker

This explicitly changes when candidate metadata changes. It indirectly changes when
`daily_bars`, `intraday_bars_1m`, `entry_day_features`, or `behavior_labels` writes update
the DuckDB file mtime/size.

Risk: if a DuckDB update changes table contents without changing file size, the token is
relying on mtime. That is probably fine locally, but it is less auditable than explicit
table fingerprints for bars/features.

### Cached Timing Rows

`load_cached_monitor_history()` returns timing rows from the cache miss that built the
history. On cache hit, Streamlit returns the cached timing rows too. The page-level
`shared monitor_history load` timing shows whether the call was cheap, but the detailed
`monitor_history detail:*` rows can look like a rebuild happened even when the cached result
was reused.

This is a diagnostic clarity issue, not a data correctness issue.

### Refresh Buttons

`refresh_derived_watchlist_views()` clears targeted derived caches:

- `load_cached_monitor_history`
- `load_data_health_summary`
- optional page-specific loaders

It does not use broad `st.cache_data.clear()`, which is good.

The downside is that clearing Data Health can make the next page render pay the full
Data Health cold cost unless that path is fixed.

## Recompute Patterns

1. Full `monitor_history()` rebuilds all setup dates even when a page only needs recent
   windows or a selected date.
2. Rolling Setup Monitor latest 5 and full shared monitor history are separate cached
   products. Opening both can compute overlapping canonical rows twice.
3. `monitor_history()` performs a second VWAP/display-trigger pass after
   `rolling_setup_monitor()` already spent about 1.9s on VWAP reclaim derivation.
4. Bar slicing is repeated inside row-level derivation. The data is small today, but this
   will scale poorly as rows/setup dates grow.
5. Data Health recomputes full canonical history on cache miss only to find active rows for
   daily-bar coverage.

## Top 5 Bottlenecks

1. Full all-date `monitor_history()` rebuild.
   Impact: High. Complexity: Medium. Risk: Medium.
   Why it matters: blocks Overview, Top Movers, Setup Performance, Daily Report, and Data
   Health cold paths.

2. Data Health cold-cache full-history dependency.
   Impact: High. Complexity: Low/Medium. Risk: Medium.
   Why it matters: a small indicator can make otherwise cheap pages feel slow.

3. Repeated row-level bar slicing and trigger derivation.
   Impact: High. Complexity: Medium. Risk: Medium.
   Why it matters: current SQL time is tiny; Python loops dominate runtime.

4. Duplicate VWAP work between Rolling Setup Monitor and `monitor_history()` display pass.
   Impact: Medium/High. Complexity: Medium. Risk: Medium.
   Why it matters: VWAP work accounts for roughly 3.9s combined in the full-history path.

5. Separate latest-5 Rolling cache and all-date shared history cache.
   Impact: Medium. Complexity: Medium. Risk: Low/Medium.
   Why it matters: useful rows can be computed twice across pages.

## Recommended Next Chunks

### A. Quick Wins

1. Remove full-history dependency from Data Health active coverage.
   Impact: High. Complexity: Low/Medium. Risk: Medium.
   Why it matters: turns Data Health from a potential 16s cold path into a lightweight SQL
   diagnostic. Keep the same displayed fields, but avoid using full canonical monitor
   history just to identify active rows.

2. Add a cached selected-date Daily Snapshot loader.
   Impact: Medium. Complexity: Low. Risk: Low.
   Why it matters: Daily Snapshot is already reasonable, but every rerun recomputes the
   selected-date monitor table. A `(db_path, setup_date, data_health_cache_token)` cache
   would make interaction cheaper.

3. Clarify cache-hit diagnostics for shared monitor history.
   Impact: Medium. Complexity: Low. Risk: Low.
   Why it matters: cached timing rows currently describe the last miss, not the current
   call. Keep page-level timing, and label detailed rows as "last cache-miss build detail"
   or return them only under an explicit debug note.

4. Avoid duplicate `data_health_cache_token(db_path)` calls within a page render.
   Impact: Low. Complexity: Low. Risk: Low.
   Why it matters: the token performs a metadata fingerprint query. It is small, but pages
   call it multiple times.

5. Keep refresh targeted.
   Impact: Medium. Complexity: Low. Risk: Low.
   Why it matters: current targeted refresh behavior is good. Do not replace it with broad
   cache clearing.

### B. Medium Changes

1. Cache canonical monitor sections per setup date.
   Impact: High. Complexity: Medium. Risk: Medium.
   Why it matters: `monitor_history()` could compose cached date-level sections instead of
   rebuilding every date. Rolling Setup Monitor latest 5, Daily Snapshot, and full history
   could share the same date-level canonical rows.

2. Pre-index daily and intraday bars by ticker/date before row derivation.
   Impact: High. Complexity: Medium. Risk: Medium.
   Why it matters: bar slicing is one of the largest costs. Pre-grouped windows would reduce
   repeated filtering.

3. Consolidate VWAP reclaim/display-trigger pass.
   Impact: Medium/High. Complexity: Medium. Risk: Medium.
   Why it matters: current full-history timings show VWAP work in both rolling derivation
   and the final history normalization pass.

4. Vectorize or batch retest/follow-through derivation.
   Impact: High. Complexity: Medium/High. Risk: Medium.
   Why it matters: retests/follow-through is currently the single largest derivation bucket.

5. Make Daily Report reuse already-prepared Top Movers rows when rendered on the Overview
   page.
   Impact: Medium. Complexity: Medium. Risk: Low/Medium.
   Why it matters: report payload assembly is about 1s and prepares/mixes portfolio views
   again.

### C. Larger Architecture Changes

1. Materialize canonical monitor history in DuckDB.
   Impact: Very High. Complexity: High. Risk: Medium/High.
   Why it matters: Streamlit pages would read durable derived rows instead of recomputing
   lifecycle/trigger/follow-through state on page render.

2. Incremental recompute by changed setup date/ticker.
   Impact: Very High. Complexity: High. Risk: High.
   Why it matters: metadata edits and new bars usually affect a small subset of canonical
   rows.

3. Split fetch, compute, and UI-read layers more formally.
   Impact: High. Complexity: High. Risk: Medium.
   Why it matters: the current pipeline already avoids API fetch during page render, but
   derived computation is still partly UI-driven.

4. Add durable derived lifecycle/status tables.
   Impact: High. Complexity: High. Risk: High.
   Why it matters: status logic is central and must remain auditable, so durable outputs
   need versioning and recompute controls.

## Suggested First Implementation Task

Start with Data Health.

Goal: make `build_data_health_summary()` avoid calling full `monitor_history()` when it only
needs active-row daily-bar coverage.

Reason: this is the clearest high-impact, relatively narrow fix. It does not need UI
changes, does not change setup metrics, and removes a hidden 16s cold path from multiple
pages.

Guardrails:

- Do not change lifecycle/status definitions.
- Keep the existing Data Health display fields.
- If exact active status is required, use shared cached history only when the page already
  has it, or add a lighter canonical active-status source as a separate follow-up.
- Add tests around the Data Health active coverage behavior before changing the logic.

## Commands Run

Timing scripts were run directly against the local DuckDB using the existing helper
functions and `PerfTimer`.

Requested test command:

```powershell
$env:WBM_PERF_DEBUG="1"
.\.venv\Scripts\python.exe -m pytest -q --basetemp=C:\Temp\wbm_pytest
```

Result: `406 passed, 34 errors`. The errors were pytest setup errors caused by
`PermissionError: [WinError 5] Access is denied: '\\?\C:\Temp\wbm_pytest'` while pytest
was cleaning the requested temp directory.

Control run with workspace-local temp directory:

```powershell
$env:WBM_PERF_DEBUG="1"
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest_tmp_wbm
```

Result: `440 passed in 23.68s`.
