from __future__ import annotations

import time

import duckdb

from src.data_health_indicator import data_health_cache_token


def test_data_health_cache_token_changes_when_db_file_changes(tmp_path):
    db_path = tmp_path / 'watchlist.duckdb'
    db_path.write_text('first')
    first = data_health_cache_token(str(db_path))

    time.sleep(0.01)
    db_path.write_text('second version')
    second = data_health_cache_token(str(db_path))

    assert first != second


def test_data_health_cache_token_changes_when_watchlist_metadata_changes(tmp_path):
    db_path = tmp_path / 'watchlist.duckdb'
    con = duckdb.connect(str(db_path))
    con.execute(
        """
        create table watchlist_candidates (
            candidate_id bigint,
            watchlist_date date,
            ticker text,
            rating double,
            setup text,
            entry_tactic text
        )
        """
    )
    con.execute("insert into watchlist_candidates values (1, '2026-05-01', 'MU', 3, 'EP', null)")
    con.close()
    first = data_health_cache_token(str(db_path))

    con = duckdb.connect(str(db_path))
    con.execute("update watchlist_candidates set rating=5, setup='Pullback', entry_tactic='Reclaim' where candidate_id=1")
    con.close()
    second = data_health_cache_token(str(db_path))

    assert first != second
