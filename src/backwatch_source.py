from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd


SUPPORTED_EXTENSIONS = {'.csv', '.xlsx', '.xls'}
CANONICAL_COLUMNS = ['ticker', 'rating', 'setup', 'focus', 'key_level']
TICKER_COLUMNS = {
    'ticker',
    'symbol',
    'symbols',
    'symbols from tc2000',
    'symbol from tc2000',
    'tc2000 symbol',
    'tc2000 symbols',
}


@dataclass(frozen=True)
class SourceFile:
    name: str
    path: Path
    modified_at: datetime
    size: int


def resolve_source_dir(path: Path, project_root: Path | None = None) -> Path:
    if path.is_absolute():
        return path
    return (project_root or Path.cwd()) / path


def list_source_files(source_dir: Path) -> list[SourceFile]:
    if not source_dir.exists():
        return []
    files = []
    for path in source_dir.iterdir():
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            stat = path.stat()
            files.append(SourceFile(path.name, path, datetime.fromtimestamp(stat.st_mtime), stat.st_size))
    return sorted(files, key=lambda f: f.modified_at, reverse=True)


def infer_setup_date(name: str) -> str | None:
    stem = Path(name).stem
    patterns = [
        (r'(?<!\d)(\d{4})[-_](\d{1,2})[-_](\d{1,2})(?!\d)', ('%Y', '%m', '%d')),
        (r'(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)', ('%Y', '%m', '%d')),
        (r'(?<!\d)(\d{1,2})-(\d{1,2})-(\d{4})(?!\d)', ('%m', '%d', '%Y')),
        (r'(?<!\d)(\d{1,2})-(\d{1,2})-(\d{2})(?!\d)', ('%m', '%d', '%y')),
    ]
    for pattern, parts in patterns:
        match = re.search(pattern, stem)
        if not match:
            continue
        values = dict(zip(parts, match.groups()))
        year = int(values['%Y']) if '%Y' in values else 2000 + int(values['%y'])
        month = int(values['%m'])
        day = int(values['%d'])
        try:
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            continue
    return None


def _read_source_file(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == '.csv':
        return pd.read_csv(path)
    return pd.read_excel(path)


def _looks_symbol_like(value) -> bool:
    text = str(value).strip().upper()
    if not text or text == 'NAN':
        return False
    return bool(re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,9}', text))


def _ticker_column(df: pd.DataFrame) -> str:
    for column in df.columns:
        if str(column).strip().lower() in TICKER_COLUMNS:
            return column
    first = df.columns[0]
    values = df[first].dropna().head(25)
    if not values.empty and values.map(_looks_symbol_like).mean() >= 0.8:
        return first
    raise ValueError('No ticker or symbol column found')


def normalize_backwatch_file(path: Path) -> pd.DataFrame:
    raw = _read_source_file(path)
    if raw.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)
    ticker_col = _ticker_column(raw)
    normalized = pd.DataFrame()
    normalized['ticker'] = raw[ticker_col].astype(str).str.upper().str.strip()
    for column in CANONICAL_COLUMNS[1:]:
        source = next((c for c in raw.columns if str(c).strip().lower() == column), None)
        normalized[column] = raw[source] if source is not None else ''
    normalized = normalized[normalized['ticker'].map(_looks_symbol_like)].copy()
    normalized = normalized.drop_duplicates(['ticker']).reset_index(drop=True)
    return normalized[CANONICAL_COLUMNS]


def canonical_filename(setup_date: str, original_stem: str) -> str:
    safe_stem = re.sub(r'[^A-Za-z0-9_.-]+', '_', original_stem).strip('._')
    return f'{setup_date}_backwatch_{safe_stem}.csv'


def save_canonical_watchlist(source_path: Path, setup_date: str, watchlists_dir: Path) -> tuple[Path, pd.DataFrame]:
    normalized = normalize_backwatch_file(source_path)
    watchlists_dir.mkdir(parents=True, exist_ok=True)
    output_path = watchlists_dir / canonical_filename(setup_date, source_path.stem)
    normalized.to_csv(output_path, index=False)
    return output_path, normalized
