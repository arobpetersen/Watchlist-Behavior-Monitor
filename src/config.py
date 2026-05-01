from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # optional dependency for local .env loading
    load_dotenv = None

if load_dotenv:
    load_dotenv()


@dataclass(frozen=True)
class Settings:
    project_root: Path = Path(__file__).resolve().parents[1]
    db_path: Path = project_root / 'data' / 'db' / 'watchlist.duckdb'
    watchlists_dir: Path = project_root / 'data' / 'watchlists'
    massive_api_key: str | None = os.getenv('MASSIVE_API_KEY')
    massive_base_url: str = os.getenv('MASSIVE_BASE_URL', 'https://api.polygon.io')
    backwatch_source_dir: Path = Path(os.getenv('BACKWATCH_SOURCE_DIR', 'tc2000'))


def get_settings() -> Settings:
    s = Settings()
    s.db_path.parent.mkdir(parents=True, exist_ok=True)
    s.watchlists_dir.mkdir(parents=True, exist_ok=True)
    return s
