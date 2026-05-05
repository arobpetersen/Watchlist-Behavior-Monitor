# Performance Notes

## Timing / Debug Output

Set `WBM_PERF_DEBUG=1` before starting Streamlit to show a collapsed
`Performance / Debug` expander on the audited pages. The expander is hidden by
default and reports coarse page-level timings for data load and display
preparation steps.

Example:

```powershell
$env:WBM_PERF_DEBUG='1'
streamlit run app.py
```

## Measured Areas

Local timing sample from the current DuckDB file:

- Data Health load: ~0.17s
- Rolling Setup Monitor data build, last 5 setup dates: ~3.05s
- Rolling Setup Monitor display prep: ~0.09s
- Setup Behavior `monitor_history` build: ~10.84s
- Setup Behavior Overview full build: ~11.48s
- Watchlist Top Movers history load: ~10.66s
- Watchlist Top Movers display prep: ~0.14s

The main cost is rebuilding monitor history across setup dates. That path
includes trigger resolution, VWAP reclaim display fields, retests, close-below-
breakeven status, and summary/detail dataframe assembly.

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

## Cache Refresh

The audited Streamlit caches refresh when the database file modified time or
file size changes, or when the page cache version string changes.

## Still Potentially Expensive

- `monitor_history()` currently builds Rolling Setup Monitor history across all
  setup dates for Setup Behavior Overview and Watchlist Top Movers.
- VWAP reclaim diagnostics and retest display fields are derived during monitor
  history construction rather than persisted as cached derived records.
- Collapsed Streamlit expanders still execute their Python bodies during a page
  rerun, so heavy detail sections should only be made lazier if a future pass can
  do so without changing user-facing behavior.

No trading logic, trigger logic, provider behavior, ingestion, or persistence
behavior was changed in this performance pass.
