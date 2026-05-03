from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd


SUPPORTED_EXTENSIONS = {'.csv', '.xlsx', '.xls'}
CANONICAL_COLUMNS = ['ticker', 'rating', 'setup', 'focus', 'key_level']
SAMPLE_NAME_KEYWORDS = {'sample', 'example', 'test'}
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


@dataclass(frozen=True)
class SourceFileStatus:
    source_file: str
    path: Path
    inferred_setup_date: str | None
    ticker_count: int | None
    status: str
    message: str
    canonical_file: str | None = None


def resolve_source_dir(path: Path, project_root: Path | None = None) -> Path:
    if path.is_absolute():
        return path
    root = project_root or Path.cwd()
    local = root / path
    sibling = root.parent / path
    if str(path).replace('\\', '/') == 'tc2000' and not local.exists() and sibling.exists():
        return sibling
    return local


def list_source_files(source_dir: Path) -> list[SourceFile]:
    if not source_dir.exists():
        return []
    files = []
    for path in source_dir.iterdir():
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            stat = path.stat()
            files.append(SourceFile(path.name, path, datetime.fromtimestamp(stat.st_mtime), stat.st_size))
    return sorted(files, key=lambda f: f.modified_at, reverse=True)


def is_sample_or_test_file(name: str) -> bool:
    stem = Path(name).stem.lower()
    parts = [p for p in re.split(r'[^a-z0-9]+', stem) if p]
    return any(keyword in parts for keyword in SAMPLE_NAME_KEYWORDS)


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


def _canonical_path(source_path: Path, setup_date: str, watchlists_dir: Path) -> Path:
    return watchlists_dir / canonical_filename(setup_date, source_path.stem)


def _already_loaded(con, setup_date: str, canonical_name: str, tickers: list[str]) -> bool:
    audited = con.execute(
        'select count(*) from watchlist_files where source_file=?',
        [canonical_name],
    ).fetchone()[0]
    if audited:
        return True
    if not tickers:
        return False
    count = con.execute(
        f"""
        select count(distinct ticker)
        from watchlist_candidates
        where watchlist_date=? and ticker in ({','.join(['?'] * len(tickers))})
        """,
        [setup_date, *tickers],
    ).fetchone()[0]
    return int(count) == len(set(tickers))


def scan_source_files(source_dir: Path, watchlists_dir: Path, con=None) -> list[SourceFileStatus]:
    statuses = []
    for source in list_source_files(source_dir):
        if is_sample_or_test_file(source.name):
            statuses.append(SourceFileStatus(source.name, source.path, None, None, 'Skipped Sample/Test', 'Sample, test, and example files are ignored.'))
            continue
        setup_date = infer_setup_date(source.name)
        if not setup_date:
            statuses.append(SourceFileStatus(source.name, source.path, None, None, 'Missing Date', 'No setup date found in filename.'))
            continue
        try:
            normalized = normalize_backwatch_file(source.path)
        except Exception as exc:
            statuses.append(SourceFileStatus(source.name, source.path, setup_date, None, 'Error', str(exc)))
            continue
        ticker_count = len(normalized)
        canonical = _canonical_path(source.path, setup_date, watchlists_dir)
        if ticker_count == 0:
            statuses.append(SourceFileStatus(source.name, source.path, setup_date, 0, 'No Valid Tickers', 'No symbol-like tickers detected.', canonical.name))
            continue
        tickers = normalized['ticker'].astype(str).tolist()
        if canonical.exists() or (con is not None and _already_loaded(con, setup_date, canonical.name, tickers)):
            statuses.append(SourceFileStatus(source.name, source.path, setup_date, ticker_count, 'Already Processed', 'Canonical file or candidate rows already exist.', canonical.name))
            continue
        statuses.append(SourceFileStatus(source.name, source.path, setup_date, ticker_count, 'New', 'Ready to process.', canonical.name))
    return sorted(
        statuses,
        key=lambda r: (r.inferred_setup_date or '9999-99-99', r.source_file),
    )


def process_new_source_files(source_dir: Path, watchlists_dir: Path, con) -> tuple[list[SourceFileStatus], list[Path]]:
    scanned = scan_source_files(source_dir, watchlists_dir, con)
    saved_paths = []
    updated = []
    for row in scanned:
        if row.status != 'New' or row.inferred_setup_date is None:
            updated.append(row)
            continue
        try:
            output_path, normalized = save_canonical_watchlist(row.path, row.inferred_setup_date, watchlists_dir)
            saved_paths.append(output_path)
            updated.append(SourceFileStatus(row.source_file, row.path, row.inferred_setup_date, len(normalized), 'Processed', f'Saved {output_path.name}.', output_path.name))
        except Exception as exc:
            updated.append(SourceFileStatus(row.source_file, row.path, row.inferred_setup_date, row.ticker_count, 'Error', str(exc), row.canonical_file))
    return updated, saved_paths


def reprocess_source_file(con, source_path: Path, watchlists_dir: Path) -> dict:
    from src.data_maintenance import remove_candidates_for_source
    from src.watchlist_ingestion import ingest_watchlists

    if is_sample_or_test_file(source_path.name):
        raise ValueError('Sample, test, and example files cannot be reprocessed into live tables.')
    setup_date = infer_setup_date(source_path.name)
    if not setup_date:
        raise ValueError('No setup date found in filename.')
    normalized = normalize_backwatch_file(source_path)
    if normalized.empty:
        raise ValueError('No symbol-like tickers detected.')

    canonical_path = _canonical_path(source_path, setup_date, watchlists_dir)
    removed = remove_candidates_for_source(con, setup_date, canonical_path.name)
    output_path, saved = save_canonical_watchlist(source_path, setup_date, watchlists_dir)
    ingest = ingest_watchlists(con, watchlists_dir, files=[output_path])
    return {
        'source_file': source_path.name,
        'setup_date': setup_date,
        'canonical_file': output_path.name,
        'old_candidates_removed': removed['candidates_removed'],
        'features_removed': removed['features_removed'],
        'labels_removed': removed['labels_removed'],
        'watchlist_file_rows_removed': removed['watchlist_file_rows_removed'],
        'new_candidates_inserted': ingest['candidates_inserted'],
        'tickers': len(saved),
        'skipped_sample_files': ingest.get('skipped_sample_files', 0),
        'failures': ingest['failures'],
    }
