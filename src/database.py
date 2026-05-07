from __future__ import annotations

import duckdb

SCHEMA_SQL = """
create table if not exists watchlist_files (
  source_file text,
  file_hash text,
  watchlist_date date,
  rows_seen integer,
  rows_inserted integer,
  ingested_at timestamp
);
create sequence if not exists candidate_seq start 1;
create table if not exists watchlist_candidates (
  candidate_id bigint,
  watchlist_date date,
  ticker text,
  rating double,
  setup text,
  entry_tactic text,
  focus text,
  key_level double,
  source_file text,
  ingested_at timestamp
);
create table if not exists intraday_bars_1m (
  ticker text,
  trading_date date,
  timestamp_et timestamp,
  open double,
  high double,
  low double,
  close double,
  volume bigint,
  source text,
  fetched_at timestamp
);
create table if not exists daily_bars (
  ticker text,
  trading_date date,
  open double,
  high double,
  low double,
  close double,
  volume bigint,
  vwap double,
  source text,
  fetched_at timestamp
);
create table if not exists entry_day_features (
  candidate_id bigint,
  watchlist_date date,
  ticker text,
  open_price double,
  high_price double,
  low_price double,
  close_price double,
  hod_time timestamp,
  lod_time timestamp,
  close_location double,
  closed_near_high boolean,
  closed_near_low boolean,
  session_vwap double,
  closed_above_vwap boolean,
  ever_below_vwap boolean,
  ever_above_vwap boolean,
  lost_vwap boolean,
  reclaimed_vwap boolean,
  vwap_reclaim_then_new_hod boolean,
  prior_close double,
  gap_pct double,
  atr20 double,
  day_range_pct double,
  range_vs_atr20 double,
  avg_volume_20d double,
  relative_volume_20d double,
  broke_entry_day_high_D1 boolean,
  broke_entry_day_low_D1 boolean,
  closed_higher_D1 boolean,
  broke_entry_day_high_within_3d boolean,
  broke_entry_day_low_within_3d boolean,
  max_gain_3d_pct double,
  max_drawdown_3d_pct double,
  or_1m json,
  or_5m json,
  or_15m json,
  calculated_at timestamp
);
create table if not exists behavior_labels (
  candidate_id bigint,
  watchlist_date date,
  ticker text,
  primary_label text,
  secondary_labels text,
  label_reason text
);
"""


def get_connection(db_path: str):
    con = duckdb.connect(db_path)
    con.execute(SCHEMA_SQL)
    for column, column_type in [
        ('entry_tactic', 'text'),
    ]:
        con.execute(f'alter table watchlist_candidates add column if not exists {column} {column_type}')
    for column, column_type in [
        ('prior_close', 'double'),
        ('gap_pct', 'double'),
        ('atr20', 'double'),
        ('day_range_pct', 'double'),
        ('range_vs_atr20', 'double'),
        ('avg_volume_20d', 'double'),
        ('relative_volume_20d', 'double'),
        ('broke_entry_day_high_D1', 'boolean'),
        ('broke_entry_day_low_D1', 'boolean'),
        ('closed_higher_D1', 'boolean'),
        ('broke_entry_day_high_within_3d', 'boolean'),
        ('broke_entry_day_low_within_3d', 'boolean'),
        ('max_gain_3d_pct', 'double'),
        ('max_drawdown_3d_pct', 'double'),
    ]:
        con.execute(f'alter table entry_day_features add column if not exists {column} {column_type}')
    return con
