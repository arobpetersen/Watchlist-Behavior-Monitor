from src.data_maintenance import remove_sample_data
from src.database import get_connection


def test_remove_sample_data_removes_candidates_features_labels_and_keeps_bars():
    con = get_connection(':memory:')
    con.execute("""
        insert into watchlist_candidates
        values
        (1, '2026-04-30', 'AAPL', null, '', '', null, 'sample_2026-04-30_watchlist.csv', current_timestamp),
        (2, '2026-04-30', 'MSFT', null, '', '', null, '2026-04-30_backwatch_real.csv', current_timestamp)
    """)
    con.execute("""
        insert into watchlist_files
        values
        ('sample_2026-04-30_watchlist.csv', 'abc', '2026-04-30', 1, 1, current_timestamp),
        ('2026-04-30_backwatch_real.csv', 'def', '2026-04-30', 1, 1, current_timestamp)
    """)
    con.execute("insert into entry_day_features (candidate_id, watchlist_date, ticker) values (1, '2026-04-30', 'AAPL')")
    con.execute("insert into behavior_labels values (1, '2026-04-30', 'AAPL', 'label', '', '')")
    con.execute("insert into intraday_bars_1m values ('AAPL', '2026-04-30', '2026-04-30 09:30:00', 1, 1, 1, 1, 1, 'test', current_timestamp)")
    con.execute("insert into daily_bars values ('AAPL', '2026-04-30', 1, 1, 1, 1, 1, null, 'test', current_timestamp)")

    summary = remove_sample_data(con)

    assert summary['candidates_removed'] == 1
    assert summary['features_removed'] == 1
    assert summary['labels_removed'] == 1
    assert summary['watchlist_file_rows_removed'] == 1
    assert con.execute('select ticker from watchlist_candidates').fetchall() == [('MSFT',)]
    assert con.execute('select count(*) from entry_day_features').fetchone()[0] == 0
    assert con.execute('select count(*) from behavior_labels').fetchone()[0] == 0
    assert con.execute('select count(*) from intraday_bars_1m').fetchone()[0] == 1
    assert con.execute('select count(*) from daily_bars').fetchone()[0] == 1
