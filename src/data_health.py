from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.backwatch_source import canonical_filename, infer_setup_date, is_sample_or_test_file, list_source_files, normalize_backwatch_file


DATA_HEALTH_COLUMNS = [
    'Setup Date',
    'Source File',
    'Canonical File',
    'Source Ticker Count',
    'DB Candidate Count',
    'Status',
    'Last Processed',
]


@dataclass(frozen=True)
class _SourceCount:
    setup_date: str
    source_file: str
    canonical_file: str
    ticker_count: int | None


def _fmt_dt(value: Any) -> str:
    if value is None:
        return '-'
    parsed = pd.to_datetime(value, errors='coerce')
    if pd.isna(parsed):
        return '-'
    return parsed.strftime('%Y-%m-%d %H:%M')


def _source_counts(source_dir: Path, watchlists_dir: Path) -> dict[tuple[str, str], _SourceCount]:
    counts = {}
    if not source_dir.exists():
        return counts
    for source in list_source_files(source_dir):
        if is_sample_or_test_file(source.name):
            continue
        setup_date = infer_setup_date(source.name)
        if not setup_date:
            continue
        canonical = canonical_filename(setup_date, source.path.stem)
        try:
            ticker_count = len(normalize_backwatch_file(source.path))
        except Exception:
            ticker_count = None
        counts[(setup_date, canonical)] = _SourceCount(setup_date, source.name, canonical, ticker_count)
    return counts


def _db_candidate_counts(con) -> dict[tuple[str, str], int]:
    rows = con.execute(
        """
        select cast(watchlist_date as varchar) as setup_date,
               source_file,
               count(distinct ticker) as candidate_count
        from watchlist_candidates
        where watchlist_date is not null and source_file is not null
        group by watchlist_date, source_file
        """
    ).fetchall()
    return {(str(setup_date), str(source_file)): int(count) for setup_date, source_file, count in rows}


def _last_processed(con) -> dict[str, str]:
    file_rows = con.execute(
        """
        select source_file, max(ingested_at) as last_processed
        from watchlist_files
        where source_file is not null
        group by source_file
        """
    ).fetchall()
    candidate_rows = con.execute(
        """
        select source_file, max(ingested_at) as last_processed
        from watchlist_candidates
        where source_file is not null
        group by source_file
        """
    ).fetchall()
    out = {str(source_file): _fmt_dt(last_processed) for source_file, last_processed in candidate_rows}
    for source_file, last_processed in file_rows:
        out[str(source_file)] = _fmt_dt(last_processed)
    return out


def data_health_rows(con, source_dir: Path, watchlists_dir: Path) -> pd.DataFrame:
    sources = _source_counts(source_dir, watchlists_dir)
    db_counts = _db_candidate_counts(con)
    processed = _last_processed(con)
    keys = sorted(set(sources) | set(db_counts), key=lambda item: (item[0], item[1]), reverse=True)
    rows = []
    for setup_date, canonical in keys:
        source = sources.get((setup_date, canonical))
        db_count = db_counts.get((setup_date, canonical), 0)
        source_count = source.ticker_count if source is not None else None

        if source is None:
            status = 'Missing Source'
        elif db_count == 0:
            status = 'Not Processed'
        elif source_count == db_count:
            status = 'OK'
        else:
            status = 'Mismatch'

        rows.append({
            'Setup Date': setup_date,
            'Source File': source.source_file if source is not None else '-',
            'Canonical File': canonical,
            'Source Ticker Count': '-' if source_count is None else source_count,
            'DB Candidate Count': db_count,
            'Status': status,
            'Last Processed': processed.get(canonical, '-'),
        })
    return pd.DataFrame(rows, columns=DATA_HEALTH_COLUMNS)
