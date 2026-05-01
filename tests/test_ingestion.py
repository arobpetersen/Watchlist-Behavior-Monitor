from pathlib import Path

from src.database import get_connection
from src.watchlist_ingestion import infer_date, ingest_watchlists


def test_infer_date():
    assert infer_date('2026-05-01_watchlist.csv') == '2026-05-01'


def test_ingest_optional_blank(tmp_path: Path):
    f = tmp_path / 'sample_2026-05-01_watchlist.csv'
    f.write_text('ticker,rating,setup,focus,key_level\nAAPL,5,,,\nMSFT,,,,\n')
    con = get_connection(':memory:')
    out = ingest_watchlists(con, tmp_path)
    assert out['candidates_inserted'] == 2
