# Data Persistence and Refresh-Safety Audit

Audit date: 2026-05-03

## Active Storage

The app stores local data in DuckDB.

- Active database path: `data/db/watchlist.duckdb`
- Resolved local path during audit: `C:\Users\arobp\OneDrive\Documents\Trade\Watchlist-Behavior-Monitor-main\Watchlist-Behavior-Monitor\data\db\watchlist.duckdb`
- Canonical internal watchlist folder: `data/watchlists`
- Configured external Back-Watch source folder: `BACKWATCH_SOURCE_DIR`, defaulting to `tc2000`
- Backup destination: `data/exports/backups/watchlist_backup_YYYY-MM-DD_HHMM.duckdb`

The active database inspected during this audit contained:

| Table | Rows | Date Range |
| --- | ---: | --- |
| `watchlist_files` | 63 | 2026-04-13 to 2026-05-01 |
| `watchlist_candidates` | 74 | 2026-04-13 to 2026-05-01 |
| `intraday_bars_1m` | 50,945 | 2026-04-13 to 2026-05-01 |
| `daily_bars` | 2,307 | 2026-02-27 to 2026-05-01 |
| `entry_day_features` | 74 | 2026-04-13 to 2026-05-01 |
| `behavior_labels` | 74 | 2026-04-13 to 2026-05-01 |

Additional integrity checks on the active DB:

- Distinct setup dates in `watchlist_candidates`: 15
- Distinct source files in `watchlist_candidates`: 15
- Duplicate candidate keys by `(watchlist_date, ticker, source_file)`: 0
- Duplicate daily bars by `(ticker, trading_date)`: 0
- Duplicate intraday bars by `(ticker, trading_date, timestamp_et)`: 0

## Table Classification

| Table | Classification | Purpose | Key Columns | Write Pattern |
| --- | --- | --- | --- | --- |
| `watchlist_candidates` | Raw/durable setup observations | One row per imported ticker/setup instance | `candidate_id`, `watchlist_date`, `ticker`, `source_file`, `setup`, `rating` | Appended on import, idempotent by query check on `(watchlist_date, ticker, source_file)`. Removed only by explicit reprocess/sample cleanup. |
| `watchlist_files` | Import ledger | Records canonical file scans/import attempts | `source_file`, `file_hash`, `watchlist_date`, `rows_seen`, `rows_inserted`, `ingested_at` | Append-style ledger. It can contain multiple rows for the same `source_file` across repeated scans. |
| `intraday_bars_1m` | Price/history data | Cached setup-day 1-minute bars | `ticker`, `trading_date`, `timestamp_et`, OHLCV | Appended only if no intraday rows exist for ticker/date. Not deleted by normal refresh or reprocess. |
| `daily_bars` | Price/history data | Cached daily bars for prior context and forward follow-through | `ticker`, `trading_date`, OHLCV | Inserts missing ticker/date rows using a `not exists` guard. Not deleted by normal refresh or reprocess. |
| `entry_day_features` | Derived/recomputable data | Entry-day OR, VWAP, ATR/context, and forward metrics | `candidate_id`, `watchlist_date`, `ticker`, OR JSON fields | Rebuilt per candidate by deleting existing row for `candidate_id`, then inserting recalculated features. |
| `behavior_labels` | Derived/recomputable data | Older/basic behavior labels for dashboard context | `candidate_id`, `watchlist_date`, `ticker`, labels | Rebuilt by deleting existing label for candidate, then inserting recalculated labels. |

There are no physical database tables dedicated to Rolling Setup Monitor, Setup Behavior Overview, or Watchlist Top Movers. Those pages derive their display rows from the durable setup observations, cached bars, and recomputable feature rows.

## Normal Import and Refresh Flow

The main app workflow starts in `app.py`.

### Process All New Back-Watch Files

1. `scan_source_files(source_dir, watchlists_dir, con)`
   - Reads the external Back-Watch source folder.
   - Marks files as `New`, `Already Processed`, `Skipped Sample/Test`, `Missing Date`, `No Valid Tickers`, or `Error`.
   - A file is considered already processed when the canonical file exists or DB candidate rows already cover its tickers.

2. `process_new_source_files(source_dir, watchlists_dir, con)`
   - Saves only files marked `New` into canonical CSVs under `data/watchlists`.
   - Does not delete existing database rows.

3. `ingest_watchlists(con, settings.watchlists_dir)`
   - Scans canonical CSV/XLSX files.
   - Inserts candidates only when `(watchlist_date, ticker, source_file)` does not already exist.
   - Adds a `watchlist_files` ledger row for each scanned canonical file.

4. `run_daily_pipeline()`, if an API key is present
   - Calls `ingest_watchlists` again, so candidate inserts remain idempotent.
   - Fetches setup-day intraday bars only when no rows exist for that ticker/date.
   - Fetches daily bars for the candidate window, then inserts only missing ticker/date rows.
   - Recalculates `entry_day_features` for candidates with available bars.
   - Rebuilds `behavior_labels` for each setup date.

### Reprocess Selected Back-Watch File

`reprocess_source_file(con, source_path, watchlists_dir)` is an explicit maintenance action.

It:

- Deletes `behavior_labels`, `entry_day_features`, `watchlist_candidates`, and `watchlist_files` rows tied to the selected canonical source file/date.
- Rewrites the canonical CSV from the selected source file.
- Re-ingests that one canonical file.
- Does not delete `daily_bars` or `intraday_bars_1m`.

### Reprocess All Source Files

This loops through real source files and applies the selected-file reprocess behavior to each. It is manual/admin behavior, not normal page load.

### Remove Sample/Test Rows

`remove_sample_data(con)` deletes sample/test/example candidates and their derived features/labels/ledger rows. It keeps cached market bars.

## Uploaded/Setup History Preservation

Confirmed behavior:

- Old setup dates remain in `watchlist_candidates` when new setup dates are imported.
- Historical setup instances are not overwritten during normal imports.
- Re-importing the same canonical file does not duplicate candidate rows because `ingest_watchlists` checks `(watchlist_date, ticker, source_file)` before insert.
- `candidate_id` is generated from `candidate_seq` and remains the durable identity for derived feature/label rows.
- `monitor_history(con)` reads all distinct setup dates from `watchlist_candidates`, calls `rolling_setup_monitor(con, setup_dates=len(dates))`, and concatenates the returned per-date monitor tables.

Important nuance:

- The import ledger table `watchlist_files` is not unique by source file. Repeated scans can append additional ledger rows with the same `source_file`, often with `rows_inserted = 0`.
- This does not duplicate candidate rows, but it means `watchlist_files` should be treated as an import-event ledger, not a unique source-file registry.

## Price/History Data Incrementality

### Intraday Bars

`run_daily_pipeline` checks:

```sql
select count(*) from intraday_bars_1m where ticker=? and trading_date=?
```

If any row exists, it skips fetching that ticker/date. This prevents duplicate inserts and avoids refetching complete intraday data during normal refresh.

Risk/limitation: if a ticker/date has partial intraday rows, the current check treats it as complete and will not repair missing minutes automatically.

### Daily Bars

For each candidate ticker/setup date, `run_daily_pipeline` requests a daily range from `watchlist_date - 45 days` through `min(watchlist_date + 7 days, today)`. It then filters out existing ticker/date rows and inserts only missing daily bars using a `not exists` guard.

This preserves existing daily history and prevents duplicate daily bars. However, provider calls are not fully scoped to only missing dates; the app may refetch a range from the provider and discard rows already cached.

## Page Data Lineage

### Rolling Setup Monitor

Source helper: `rolling_setup_monitor(con, setup_dates=5)`

Reads:

- `watchlist_candidates`
- `entry_day_features`
- `daily_bars`
- `intraday_bars_1m`

Behavior:

- Uses the latest N setup dates by default on the page.
- Recomputes display/classification rows from durable candidates and cached bars.
- Does not write rows during page load, except the edit/rating helper can update `watchlist_candidates.setup` and `watchlist_candidates.rating` when the user submits edits.

### Setup Behavior Overview

Source helper: `setup_behavior_overview(con)`

Reads:

- Setup dates from `watchlist_candidates`
- Full historical monitor rows through `monitor_history(con)`

Behavior:

- Uses actual historical setup dates from the database.
- Builds Last 5/10/20 setup-date windows from durable candidates.
- Derived metrics are recomputable from `watchlist_candidates`, `entry_day_features`, `daily_bars`, and `intraday_bars_1m`.
- Does not write to the database.

### Watchlist Top Movers

Source helper: `load_top_movers(con)` -> `monitor_history(con)`

Reads:

- Same monitor-history lineage as Setup Behavior Overview.
- Latest available market date from `daily_bars`.

Behavior:

- Uses durable setup history via `watchlist_candidates`, not a latest-only table.
- `Setup Window = All` includes old setup dates as long as they remain in `watchlist_candidates`.
- The active movers table is intentionally built from all available setup dates and is independent of the setup-window filter.
- Does not write to the database.

### Daily Snapshot, Rolling Behavior, Ticker Detail

These pages use older/basic query helpers in `dashboard_queries.py` and direct reads from `watchlist_candidates`, `entry_day_features`, and `behavior_labels`. They do not currently use the refined Rolling Setup Monitor trigger classifications as their source of truth.

## Destructive/Rebuild Operation Inventory

| Operation | Location | Tables Affected | Normal App Usage? | Risk | Safeguard |
| --- | --- | --- | --- | --- | --- |
| Delete and rebuild candidate-derived features | `feature_engine.compute_features` | `entry_day_features` | Yes, during metrics pipeline | Low. Derived/recomputable per `candidate_id`. | Durable candidates and bars remain. |
| Delete and rebuild behavior labels | `behavior_labels.assign_labels_for_date` | `behavior_labels` | Yes, during metrics pipeline | Low. Derived/recomputable. | Durable candidates/features remain. |
| Reprocess selected source | `backwatch_source.reprocess_source_file` -> `data_maintenance.remove_candidates_for_source` | `watchlist_candidates`, `watchlist_files`, `entry_day_features`, `behavior_labels` for one source/date | Manual Maintenance only | Medium. Intentionally replaces one source file's candidates. | DB backup button exists; cached bars retained. |
| Reprocess all source files | `app.py` maintenance flow | Same as selected source, repeated | Manual Maintenance only | Medium/high if source folder is wrong. | DB backup button exists but is not required automatically. |
| Remove sample/test rows | `data_maintenance.remove_sample_data` | sample/test rows in `watchlist_candidates`, `watchlist_files`, `entry_day_features`, `behavior_labels` | Manual Maintenance only | Low, scoped by source filename keywords. | Cached bars retained. |
| Update setup/rating | `rolling_setup_monitor.update_candidate_metadata` | `watchlist_candidates.setup`, `watchlist_candidates.rating` | Manual edit only | Low, explicit user edit. | No backup required. |
| Schema creation/migration | `database.get_connection` | Creates tables if missing; adds feature columns | Normal app connection | Low. Non-destructive `create table if not exists` and `alter table add column if not exists`. | Existing data preserved. |

No `DROP TABLE`, `TRUNCATE`, or `CREATE OR REPLACE` operations were found in application code.

## Confirmed Guarantees

- Uploaded setup candidates persist across normal imports and refreshes.
- Re-importing the same file does not duplicate `watchlist_candidates`.
- Importing a new setup date preserves previous setup dates.
- Rolling Setup Monitor, Setup Behavior Overview, and Watchlist Top Movers are derived from durable candidate history and cached price data.
- Normal refresh does not delete `daily_bars` or `intraday_bars_1m`.
- Explicit reprocess deletes candidates/features/labels for targeted source files but keeps cached market bars.
- A DB backup utility exists before manual maintenance work.

## Identified Risks and Nuances

1. `watchlist_files` is an event ledger, not a unique source registry.
   - Repeated scans can append multiple rows for the same canonical file.
   - Current Data Health uses max processed timestamp, so duplicate ledger rows are not harmful for display.
   - If future code treats one row as one unique source file, it should aggregate by `source_file`.

2. Candidate idempotency is enforced in code, not by a DuckDB unique constraint.
   - Current import logic checks `(watchlist_date, ticker, source_file)` before insert.
   - A future import path that bypasses `ingest_watchlists` could create duplicates.

3. Intraday refresh treats any existing ticker/date rows as complete.
   - This avoids refetching, but it can leave partial data uncorrected unless rows are manually removed or a repair mode is added.

4. Daily refresh prevents duplicate inserts, but provider calls are broader than strictly missing rows.
   - It fetches the full candidate date window and filters existing bars after the response.
   - This is safe for persistence but not perfectly optimized for API usage.

5. Reprocess All Source Files is intentionally destructive for candidates/features/labels.
   - It is manual and keeps bars.
   - Consider creating a backup automatically before this action if the workflow becomes frequent.

## Recommended Next Actions

No urgent persistence fix is required before continuing feature work.

Small future hardening options:

1. Treat `watchlist_files` explicitly as an import-event ledger in docs/UI, or add a unique source registry if needed later.
2. Add database-level uniqueness checks or dedupe tests around `(watchlist_date, ticker, source_file)` for candidates and `(ticker, trading_date)` for daily bars.
3. Add an optional intraday repair mode that detects partial ticker/date sessions before skipping fetches.
4. Add automatic DB backup before `Reprocess All Source Files`.
5. Scope daily API calls to missing date ranges if API usage becomes a concern.

