# Performance Notes

## Timing / Debug Output

Set `WBM_PERF_DEBUG=1` before starting Streamlit to show a collapsed
`Performance / Debug` expander on the audited pages. The expander is hidden by
default. It now reports page-level timings plus cache-miss detail from the heavy
builders, including SQL reads, trigger derivation, VWAP reclaim derivation,
retest/follow-through work, status/close-below-BE work, page aggregation, and
display-prep steps.

Example:

```powershell
$env:WBM_PERF_DEBUG='1'
streamlit run app.py
```

## Measured Areas

Baseline local timing sample from the current DuckDB file before this pass:

- Data Health load: ~0.17s
- Rolling Setup Monitor data build, last 5 setup dates: ~3.05s
- Rolling Setup Monitor display prep: ~0.09s
- Setup Behavior `monitor_history` build: ~10.84s
- Setup Behavior Overview full build: ~11.48s
- Watchlist Top Movers history load: ~10.66s
- Watchlist Top Movers display prep: ~0.14s

Current local timing sample after this pass:

- Rolling Setup Monitor data build, last 5 setup dates: ~2.84s
- Shared `monitor_history` dynamic build, all setup dates: ~11.80s
- Setup Behavior Overview aggregation from prebuilt history: ~0.81s
- Watchlist Top Movers load from prebuilt history: ~0.01s
- Watchlist Top Movers base row mapping once: ~0.07s
- Watchlist Top Movers active/triggered display prep from mapped rows: ~0.04-0.05s each

Detailed `monitor_history` sample:

- SQL setup-date/candidate/daily/intraday reads: ~0.05s total
- Bar slicing by ticker/date: ~1.91s
- Trigger resolution: ~1.86s
- ORH/PDH trigger derivation: ~2.28s
- VWAP reclaim derivation inside Rolling Setup Monitor: ~1.53s
- Retests/follow-through derivation: ~2.13s
- Close < BE/status/notes: ~0.03s
- Section dataframe formatting: ~0.56s
- Additional raw VWAP reclaim pass for monitor history display fields: ~1.36s

The main cost is not SQL. It is rebuilding derived monitor history across setup
dates. That path includes trigger resolution, ORH/PDH derivation, VWAP reclaim
display fields, retests/follow-through, close-below-breakeven status, and
summary/detail dataframe assembly.

## Optimizations Added

- Rolling Setup Monitor now uses a Streamlit page data cache keyed by:
  - DB path
  - DB file modified time
  - DB file size
  - page cache version
- Setup Behavior Overview now uses the same DB mtime/size cache-token pattern
  instead of only a static cache version.
- Watchlist Top Movers already used the DB-backed cache-token pattern; timing
  instrumentation was added around its expensive load and display-prep steps.
- Timing instrumentation was added for:
  - DB connection/open where applicable
  - Data Health load
  - Rolling Setup Monitor data build
  - Setup Behavior Overview data build
  - Watchlist Top Movers data build
  - visible/display dataframe preparation
- Heavy-builder timing instrumentation was added for:
  - SQL load time by setup-date/candidate/daily/intraday query
  - VWAP reclaim derivation
  - ORH/PDH trigger derivation
  - Retests/follow-through derivation
  - Close < BE/status/notes derivation
  - Trigger resolution
  - Page-specific aggregation and formatting
- Setup Behavior Overview and Watchlist Top Movers now share a single
  Streamlit-cached `monitor_history` loader keyed by the DB mtime/size token.
  If one page has already populated the shared history cache, the other page can
  reuse it instead of rebuilding the same ~10-12s derived history.
- Watchlist Top Movers now maps its base display rows once per page load and
  reuses the mapped rows for the active/portfolio and triggered-movers tables.

## Cache Refresh

The audited Streamlit caches refresh when the database file modified time or
file size changes, or when the page cache version string changes.

Cache behavior by page:

- Rolling Setup Monitor: `load_rolling_setup_sections(db_path,
  rolling_cache_token)`, keyed by DB path plus `ROLLING_MONITOR_CACHE_VERSION`
  and `data_health_cache_token(db_path)`.
- Setup Behavior Overview: shared `load_cached_monitor_history(db_path,
  monitor_history_cache_token)` plus page aggregation
  `load_setup_behavior_overview(db_path, overview_cache_token, _history)`.
- Watchlist Top Movers: shared `load_cached_monitor_history(db_path,
  monitor_history_cache_token)` plus `load_watchlist_top_movers(db_path,
  top_movers_cache_token, _history)`.
- Manual ingest/reprocess/edit/save operations write the DuckDB file, so the
  mtime/size token changes and the Streamlit caches invalidate on rerun.
- On cache hit, the cached functions do not recompute the expensive builder.
  Timing rows returned from cached functions describe the cache population run.

## Still Potentially Expensive

- `monitor_history()` still dynamically builds Rolling Setup Monitor history
  across all setup dates when the shared cache is cold.
- VWAP reclaim diagnostics and retest display fields are still derived during
  monitor history construction rather than persisted as cached derived records.
- Collapsed Streamlit expanders still execute their Python bodies during a page
  rerun, so heavy detail sections should only be made lazier if a future pass can
  do so without changing user-facing behavior.

## Duplicate Work Found

- Setup Behavior Overview and Watchlist Top Movers both rebuilt
  `monitor_history(con)` independently.
- Watchlist Top Movers called its display-mapping helper twice per page load:
  once for all active/portfolio rows and once for filtered triggered rows.
- VWAP reclaim fields are derived once inside Rolling Setup Monitor and then raw
  VWAP diagnostics are reattached in the full monitor-history pass. This remains
  a candidate for derived-history materialization.

## Materialized Derived History Feasibility

A recomputable `derived_monitor_history` or `monitor_history_cache` table is
feasible, but it was deferred from this pass. Stable candidates include:

- candidate id, ticker, setup date, setup, rating, source fields
- trigger day, current status, resolved trigger, PDH, 1m ORH, 5m ORH, qualified
  VWAP reclaim, close < BE, retests
- current/max/D3 percentages and audit fields already produced by
  `rolling_setup_monitor`

Recommended Phase 2:

1. Add a derived table with a schema version and input fingerprint per
   candidate/setup date.
2. Rebuild affected rows after ingest, reprocess, market-data refresh, and
   manual setup/rating edits.
3. Let pages read the derived table when all rows are current, with fallback to
   the dynamic builder when the table is missing or stale.
4. Keep source of truth unchanged: `watchlist_candidates`, bars, and
   `entry_day_features`.

This should reduce cold page reads to sub-second SQL plus display prep after the
derived table has been rebuilt. It was not implemented here because it adds a
new persistence lifecycle and needs a careful invalidation contract. No trading
logic, trigger logic, provider behavior, ingestion semantics, or source-of-truth
persistence behavior was changed in this performance pass.
