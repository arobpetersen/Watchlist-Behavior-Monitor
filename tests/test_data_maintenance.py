from src.data_maintenance import (
    find_orphaned_watchlist_sources,
    preview_watchlist_source_removal,
    remove_sample_data,
    remove_watchlist_source,
)
from src.database import get_connection
from src.watchlist_ingestion import ingest_watchlists


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


def test_preview_watchlist_source_removal_shows_candidate_and_derived_counts():
    con = get_connection(':memory:')
    con.execute("""
        insert into watchlist_candidates
        values
        (10, '2026-05-02', 'CRML', null, '', '', null, '2026-05-02_backwatch_stale.csv', current_timestamp),
        (11, '2026-05-02', 'AAPL', null, '', '', null, '2026-05-02_backwatch_stale.csv', current_timestamp),
        (12, '2026-05-04', 'MSFT', null, '', '', null, '2026-05-04_backwatch_good.csv', current_timestamp)
    """)
    con.execute("""
        insert into watchlist_files
        values
        ('2026-05-02_backwatch_stale.csv', 'abc', '2026-05-02', 2, 2, current_timestamp),
        ('2026-05-04_backwatch_good.csv', 'def', '2026-05-04', 1, 1, current_timestamp)
    """)
    con.execute("insert into entry_day_features (candidate_id, watchlist_date, ticker) values (10, '2026-05-02', 'CRML')")
    con.execute("insert into behavior_labels values (11, '2026-05-02', 'AAPL', 'label', '', '')")

    preview = preview_watchlist_source_removal(con, '2026-05-02_backwatch_stale.csv')

    assert preview['source_file'] == '2026-05-02_backwatch_stale.csv'
    assert preview['candidate_rows'] == 2
    assert preview['distinct_tickers'] == 2
    assert preview['watchlist_date_min'] == '2026-05-02'
    assert preview['watchlist_date_max'] == '2026-05-02'
    assert preview['entry_day_features_rows'] == 1
    assert preview['behavior_labels_rows'] == 1
    assert preview['watchlist_file_rows'] == 1
    assert 'AAPL' in preview['sample_tickers']
    assert 'CRML' in preview['sample_tickers']


def test_remove_watchlist_source_deletes_only_selected_source_and_keeps_bars():
    con = get_connection(':memory:')
    con.execute("""
        insert into watchlist_candidates
        values
        (20, '2026-05-02', 'CRML', null, '', '', null, '2026-05-02_backwatch_stale.csv', current_timestamp),
        (21, '2026-05-02', 'CRML', null, '', '', null, '2026-05-02_backwatch_good.csv', current_timestamp),
        (22, '2026-05-04', 'AAPL', null, '', '', null, '2026-05-04_backwatch_good.csv', current_timestamp)
    """)
    con.execute("""
        insert into watchlist_files
        values
        ('2026-05-02_backwatch_stale.csv', 'abc', '2026-05-02', 1, 1, current_timestamp),
        ('2026-05-02_backwatch_good.csv', 'def', '2026-05-02', 1, 1, current_timestamp),
        ('2026-05-04_backwatch_good.csv', 'ghi', '2026-05-04', 1, 1, current_timestamp)
    """)
    con.execute("insert into entry_day_features (candidate_id, watchlist_date, ticker) values (20, '2026-05-02', 'CRML')")
    con.execute("insert into entry_day_features (candidate_id, watchlist_date, ticker) values (21, '2026-05-02', 'CRML')")
    con.execute("insert into behavior_labels values (20, '2026-05-02', 'CRML', 'label', '', '')")
    con.execute("insert into intraday_bars_1m values ('CRML', '2026-05-02', '2026-05-02 09:30:00', 1, 1, 1, 1, 1, 'test', current_timestamp)")
    con.execute("insert into daily_bars values ('CRML', '2026-05-02', 1, 1, 1, 1, 1, null, 'test', current_timestamp)")

    summary = remove_watchlist_source(con, '2026-05-02_backwatch_stale.csv')

    assert summary['candidates_removed'] == 1
    assert summary['features_removed'] == 1
    assert summary['labels_removed'] == 1
    assert summary['watchlist_file_rows_removed'] == 1
    assert con.execute('select source_file from watchlist_candidates order by source_file').fetchall() == [
        ('2026-05-02_backwatch_good.csv',),
        ('2026-05-04_backwatch_good.csv',),
    ]
    assert con.execute('select candidate_id from entry_day_features').fetchall() == [(21,)]
    assert con.execute('select count(*) from behavior_labels').fetchone()[0] == 0
    assert con.execute('select count(*) from watchlist_files').fetchone()[0] == 2
    assert con.execute('select count(*) from intraday_bars_1m').fetchone()[0] == 1
    assert con.execute('select count(*) from daily_bars').fetchone()[0] == 1


def test_reimporting_corrected_file_after_source_cleanup_works(tmp_path):
    con = get_connection(':memory:')
    stale = tmp_path / '2026-05-01_backwatch_stale.csv'
    stale.write_text('ticker,rating,setup,focus,key_level\nCRML,1,EP,,10\n')
    result = ingest_watchlists(con, tmp_path, files=[stale])
    assert result['candidates_inserted'] == 1

    cleanup = remove_watchlist_source(con, stale.name)
    assert cleanup['candidates_removed'] == 1

    corrected = tmp_path / '2026-05-04_backwatch_corrected.csv'
    corrected.write_text('ticker,rating,setup,focus,key_level\nCRML,1,EP,,10\n')
    result = ingest_watchlists(con, tmp_path, files=[corrected])

    assert result['candidates_inserted'] == 1
    assert con.execute(
        'select cast(watchlist_date as varchar), ticker, source_file from watchlist_candidates'
    ).fetchall() == [('2026-05-04', 'CRML', corrected.name)]


def test_orphaned_watchlist_sources_find_imports_missing_from_folder(tmp_path):
    con = get_connection(':memory:')
    present = tmp_path / '2026-05-04_backwatch_present.csv'
    present.write_text('ticker\nAAPL\n')
    con.execute("""
        insert into watchlist_candidates
        values
        (30, '2026-05-02', 'CRML', null, '', '', null, '2026-05-02_backwatch_missing.csv', current_timestamp),
        (31, '2026-05-04', 'AAPL', null, '', '', null, '2026-05-04_backwatch_present.csv', current_timestamp)
    """)
    con.execute("""
        insert into watchlist_files
        values
        ('2026-05-02_backwatch_missing.csv', 'abc', '2026-05-02', 1, 1, current_timestamp),
        ('2026-05-04_backwatch_present.csv', 'def', '2026-05-04', 1, 1, current_timestamp)
    """)

    orphaned = find_orphaned_watchlist_sources(con, tmp_path)

    assert orphaned['source_file'].tolist() == ['2026-05-02_backwatch_missing.csv']
    assert orphaned['candidate_rows'].tolist() == [1]
    assert orphaned['distinct_tickers'].tolist() == [1]
