from pathlib import Path

from src.database import get_connection
from src.watchlist_ingestion import infer_date, ingest_watchlists


def test_infer_date():
    assert infer_date('2026-05-01_watchlist.csv') == '2026-05-01'


def test_ingest_optional_blank(tmp_path: Path):
    f = tmp_path / '2026-05-01_watchlist.csv'
    f.write_text('ticker,rating,setup,focus,key_level\nAAPL,5,,,\nMSFT,,,,\n')
    con = get_connection(':memory:')
    out = ingest_watchlists(con, tmp_path)
    assert out['candidates_inserted'] == 2


def test_reimporting_same_watchlist_does_not_duplicate_candidates(tmp_path: Path):
    f = tmp_path / '2026-05-01_watchlist.csv'
    f.write_text('ticker\nAAPL\nMSFT\n')
    con = get_connection(':memory:')

    first = ingest_watchlists(con, tmp_path)
    second = ingest_watchlists(con, tmp_path)

    assert first['candidates_inserted'] == 2
    assert second['candidates_inserted'] == 0
    assert con.execute('select count(*) from watchlist_candidates').fetchone()[0] == 2
    assert con.execute('''
        select count(*)
        from (
            select watchlist_date, ticker, source_file, count(*) as rows
            from watchlist_candidates
            group by watchlist_date, ticker, source_file
            having count(*) > 1
        )
    ''').fetchone()[0] == 0


def test_importing_new_setup_date_preserves_prior_setup_dates(tmp_path: Path):
    first_file = tmp_path / '2026-05-01_watchlist.csv'
    second_file = tmp_path / '2026-05-02_watchlist.csv'
    first_file.write_text('ticker\nAAPL\n')
    con = get_connection(':memory:')

    ingest_watchlists(con, tmp_path, files=[first_file])
    second_file.write_text('ticker\nMSFT\n')
    ingest_watchlists(con, tmp_path, files=[second_file])

    rows = con.execute('select cast(watchlist_date as varchar), ticker from watchlist_candidates order by watchlist_date, ticker').fetchall()
    assert rows == [('2026-05-01', 'AAPL'), ('2026-05-02', 'MSFT')]


def test_ingest_skips_sample_test_example_files(tmp_path: Path):
    (tmp_path / 'sample_2026-05-01_watchlist.csv').write_text('ticker\nAAPL\n')
    (tmp_path / '2026-05-01_test_watchlist.csv').write_text('ticker\nMSFT\n')
    (tmp_path / 'example_2026-05-01_watchlist.csv').write_text('ticker\nNVDA\n')
    (tmp_path / '2026-05-01_watchlist.csv').write_text('ticker\nTSLA\n')
    con = get_connection(':memory:')

    out = ingest_watchlists(con, tmp_path)

    assert out['skipped_sample_files'] == 3
    assert out['candidates_inserted'] == 1
    assert con.execute('select ticker from watchlist_candidates').fetchall() == [('TSLA',)]
