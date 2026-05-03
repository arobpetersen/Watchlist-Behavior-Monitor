from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.db_backup import backup_path, create_db_backup


def test_backup_path_uses_expected_backup_directory_and_timestamp(tmp_path: Path):
    db_path = tmp_path / 'data' / 'db' / 'watchlist.duckdb'
    exports_dir = tmp_path / 'data' / 'exports'
    now = datetime(2026, 5, 3, 14, 7)

    path = backup_path(db_path, exports_dir, now)

    assert path == exports_dir / 'backups' / 'watchlist_backup_2026-05-03_1407.duckdb'


def test_create_db_backup_copies_duckdb_file(tmp_path: Path):
    db_path = tmp_path / 'watchlist.duckdb'
    db_path.write_bytes(b'duckdb-bytes')
    exports_dir = tmp_path / 'exports'

    path = create_db_backup(db_path, exports_dir, datetime(2026, 5, 3, 14, 7))

    assert path.exists()
    assert path.read_bytes() == b'duckdb-bytes'
    assert path.name == 'watchlist_backup_2026-05-03_1407.duckdb'
