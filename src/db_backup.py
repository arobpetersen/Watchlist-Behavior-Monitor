from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def backup_path(db_path: Path, exports_dir: Path, now: datetime | None = None) -> Path:
    stamp = (now or datetime.now()).strftime('%Y-%m-%d_%H%M')
    return exports_dir / 'backups' / f'watchlist_backup_{stamp}.duckdb'


def create_db_backup(db_path: Path, exports_dir: Path, now: datetime | None = None) -> Path:
    if not db_path.exists():
        raise FileNotFoundError(f'DuckDB file not found: {db_path}')
    target = backup_path(db_path, exports_dir, now)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path, target)
    return target
