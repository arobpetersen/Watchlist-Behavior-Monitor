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
