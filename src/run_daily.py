from __future__ import annotations

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
    else:
        failures.append('API key missing')

    for _, c in cands.iterrows():
        features += int(compute_features(con, c.to_dict()))
    for d in cands['watchlist_date'].dropna().astype(str).unique().tolist():
        labels += assign_labels_for_date(con, d)

    print('Run Summary')
    print(f"- files scanned: {ingest['files_scanned']}")
    print(f"- candidates inserted: {ingest['candidates_inserted']}")
    print(f'- bars fetched: {bars}')
    print(f'- features calculated: {features}')
    print(f'- labels assigned: {labels}')
    print(f'- failures: {len(failures)}')
    for f in failures:
        print(f'  * {f}')


if __name__ == '__main__':
    main()
