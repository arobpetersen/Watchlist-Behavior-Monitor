from src.config import get_settings
from src.database import get_connection


def main():
    s = get_settings()
    con = get_connection(str(s.db_path))
    print(f'DB path: {s.db_path.resolve()}')
    for t in ['watchlist_files','watchlist_candidates','intraday_bars_1m','daily_bars','entry_day_features','behavior_labels']:
        print(f"{t}: {con.execute(f'select count(*) from {t}').fetchone()[0]}")
    sample_candidates = con.execute("""
        select count(*)
        from watchlist_candidates
        where lower(source_file) like '%sample%'
           or lower(source_file) like '%example%'
           or lower(source_file) like '%test%'
    """).fetchone()[0]
    latest_dates = [
        str(r[0])
        for r in con.execute(
            'select distinct watchlist_date from watchlist_candidates where watchlist_date is not null order by watchlist_date desc limit 5'
        ).fetchall()
    ]
    print(f'sample/test/example candidates: {sample_candidates}')
    print(f"latest setup dates: {', '.join(latest_dates) if latest_dates else ''}")


if __name__ == '__main__':
    main()
