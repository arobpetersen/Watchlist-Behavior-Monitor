from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from src.behavior_labels import assign_labels_for_date
from src.config import get_settings
from src.database import get_connection
from src.feature_engine import compute_features
from src.massive_client import MassiveClient
from src.watchlist_ingestion import ingest_watchlists


def main():
    s = get_settings()
    con = get_connection(str(s.db_path))
    print(f'DB path: {s.db_path.resolve()}')
    ingest = ingest_watchlists(con, s.watchlists_dir)
    cands = con.execute('select candidate_id,watchlist_date,ticker from watchlist_candidates where watchlist_date is not null').df()
    bars, features, labels, failures = 0, 0, 0, list(ingest['failures'])
    daily_bars_fetched, daily_bars_skipped_existing, forward_stats_calculated = 0, 0, 0

    if s.massive_api_key:
        client = MassiveClient(s.massive_api_key, s.massive_base_url)
        for _, c in cands.iterrows():
            try:
                exists = con.execute('select count(*) from intraday_bars_1m where ticker=? and trading_date=?', [c['ticker'], str(c['watchlist_date'])]).fetchone()[0]
                if exists:
                    continue
                df = client.fetch_intraday_1m(c['ticker'], c['watchlist_date'])
                if df.empty:
                    continue
                con.register('bars', df)
                con.execute('insert into intraday_bars_1m select * from bars')
                bars += len(df)
            except Exception as e:
                failures.append(str(e))
        today = datetime.utcnow().date()
        daily_requests = cands[['ticker','watchlist_date']].drop_duplicates()
        for _, c in daily_requests.iterrows():
            try:
                watchlist_date = pd.to_datetime(c['watchlist_date']).date()
                from_date = watchlist_date - timedelta(days=45)
                to_date = min(watchlist_date + timedelta(days=7), today)
                df = client.fetch_daily(c['ticker'], from_date, to_date)
                if df.empty:
                    continue
                existing_dates = {
                    str(r[0])
                    for r in con.execute(
                        'select trading_date from daily_bars where ticker=? and trading_date between ? and ?',
                        [c['ticker'], str(from_date), str(to_date)],
                    ).fetchall()
                }
                new_df = df[~df['trading_date'].astype(str).isin(existing_dates)].copy()
                daily_bars_fetched += len(df)
                daily_bars_skipped_existing += len(df) - len(new_df)
                if new_df.empty:
                    continue
                con.register('daily', new_df)
                con.execute('''
                    insert into daily_bars
                    select ticker,trading_date,open,high,low,close,volume,vwap,source,fetched_at
                    from daily d
                    where not exists (
                        select 1 from daily_bars b
                        where b.ticker=d.ticker and b.trading_date=d.trading_date
                    )
                ''')
            except Exception as e:
                failures.append(str(e))
    else:
        failures.append('API key missing')

    for _, c in cands.iterrows():
        calculated = compute_features(con, c.to_dict())
        features += int(calculated)
        if calculated:
            has_forward = con.execute('''
                select broke_entry_day_high_D1 is not null
                    or broke_entry_day_low_D1 is not null
                    or broke_entry_day_high_within_3d is not null
                    or broke_entry_day_low_within_3d is not null
                from entry_day_features where candidate_id=?
            ''', [int(c['candidate_id'])]).fetchone()
            forward_stats_calculated += int(bool(has_forward and has_forward[0]))
    for d in cands['watchlist_date'].dropna().astype(str).unique().tolist():
        labels += assign_labels_for_date(con, d)

    print('Run Summary')
    print(f"- files scanned: {ingest['files_scanned']}")
    print(f"- candidates inserted: {ingest['candidates_inserted']}")
    print(f'- bars fetched: {bars}')
    print(f'- daily_bars_fetched: {daily_bars_fetched}')
    print(f'- daily_bars_skipped_existing: {daily_bars_skipped_existing}')
    print(f'- features calculated: {features}')
    print(f'- forward_stats_calculated: {forward_stats_calculated}')
    print(f'- labels assigned: {labels}')
    print(f'- failures: {len(failures)}')
    for f in failures:
        print(f'  * {f}')


if __name__ == '__main__':
    main()
