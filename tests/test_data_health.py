from __future__ import annotations

from pathlib import Path

from src.backwatch_source import canonical_filename
from src.data_health import DATA_HEALTH_COLUMNS, data_health_rows
from src.database import get_connection


def _insert_candidate(con, candidate_id: int, setup_date: str, ticker: str, source_file: str):
    con.execute(
        """
        insert into watchlist_candidates
        values (?, ?, ?, null, '', '', null, ?, current_timestamp)
        """,
        [candidate_id, setup_date, ticker, source_file],
    )


def test_data_health_status_ok_when_source_and_db_counts_match(tmp_path: Path):
    source_dir = tmp_path / 'tc2000'
    watchlists_dir = tmp_path / 'watchlists'
    source_dir.mkdir()
    watchlists_dir.mkdir()
    source = source_dir / '2026-05-01_backwatch.csv'
    source.write_text('ticker\nAAPL\nMSFT\n')
    canonical = canonical_filename('2026-05-01', source.stem)
    con = get_connection(':memory:')
    _insert_candidate(con, 1, '2026-05-01', 'AAPL', canonical)
    _insert_candidate(con, 2, '2026-05-01', 'MSFT', canonical)
    con.execute(
        "insert into watchlist_files values (?, 'hash', '2026-05-01', 2, 2, current_timestamp)",
        [canonical],
    )

    rows = data_health_rows(con, source_dir, watchlists_dir)

    assert rows.columns.tolist() == DATA_HEALTH_COLUMNS
    assert rows.loc[0, 'Setup Date'] == '2026-05-01'
    assert rows.loc[0, 'Source File'] == source.name
    assert rows.loc[0, 'Canonical File'] == canonical
    assert rows.loc[0, 'Source Ticker Count'] == 2
    assert rows.loc[0, 'DB Candidate Count'] == 2
    assert rows.loc[0, 'Status'] == 'OK'
    assert rows.loc[0, 'Last Processed'] != '-'


def test_data_health_status_mismatch_when_counts_differ(tmp_path: Path):
    source_dir = tmp_path / 'tc2000'
    watchlists_dir = tmp_path / 'watchlists'
    source_dir.mkdir()
    watchlists_dir.mkdir()
    source = source_dir / '2026-05-01_backwatch.csv'
    source.write_text('ticker\nAAPL\nMSFT\n')
    canonical = canonical_filename('2026-05-01', source.stem)
    con = get_connection(':memory:')
    _insert_candidate(con, 1, '2026-05-01', 'AAPL', canonical)

    rows = data_health_rows(con, source_dir, watchlists_dir)

    assert rows.loc[0, 'Source Ticker Count'] == 2
    assert rows.loc[0, 'DB Candidate Count'] == 1
    assert rows.loc[0, 'Status'] == 'Mismatch'


def test_data_health_status_missing_source_and_not_processed(tmp_path: Path):
    source_dir = tmp_path / 'tc2000'
    watchlists_dir = tmp_path / 'watchlists'
    source_dir.mkdir()
    watchlists_dir.mkdir()
    existing_source = source_dir / '2026-05-02_backwatch.csv'
    existing_source.write_text('ticker\nNVDA\n')
    missing_canonical = canonical_filename('2026-05-01', '2026-05-01_backwatch')
    con = get_connection(':memory:')
    _insert_candidate(con, 1, '2026-05-01', 'AAPL', missing_canonical)

    rows = data_health_rows(con, source_dir, watchlists_dir)
    by_status = {row['Status']: row for _, row in rows.iterrows()}

    assert by_status['Missing Source']['Canonical File'] == missing_canonical
    assert by_status['Missing Source']['Source File'] == '-'
    assert by_status['Not Processed']['Source File'] == existing_source.name
    assert by_status['Not Processed']['DB Candidate Count'] == 0
