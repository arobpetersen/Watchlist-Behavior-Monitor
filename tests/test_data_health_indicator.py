from __future__ import annotations

import time

from src.data_health_indicator import data_health_cache_token


def test_data_health_cache_token_changes_when_db_file_changes(tmp_path):
    db_path = tmp_path / 'watchlist.duckdb'
    db_path.write_text('first')
    first = data_health_cache_token(str(db_path))

    time.sleep(0.01)
    db_path.write_text('second version')
    second = data_health_cache_token(str(db_path))

    assert first != second
