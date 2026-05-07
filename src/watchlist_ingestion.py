from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.backwatch_source import infer_setup_date, is_sample_or_test_file, is_weekend_setup_date, weekend_setup_date_message


def infer_date(name: str) -> str | None:
    return infer_setup_date(name)


def ingest_watchlists(con, watchlists_dir: Path, files: list[Path] | None = None) -> dict:
    if files is None:
        files = sorted([*watchlists_dir.glob('*.csv'), *watchlists_dir.glob('*.xlsx')])
    else:
        files = sorted([Path(f) for f in files])
    inserted, failures = 0, []
    skipped_sample_files = 0
    skipped_weekend_files = 0
    for f in files:
        if is_sample_or_test_file(f.name):
            skipped_sample_files += 1
            continue
        rows_seen, rows_inserted = 0, 0
        d = infer_date(f.name)
        if is_weekend_setup_date(d):
            skipped_weekend_files += 1
            failures.append(weekend_setup_date_message(d, f))
            continue
        h = hashlib.sha256(f.read_bytes()).hexdigest()
        try:
            df = pd.read_csv(f) if f.suffix.lower() == '.csv' else pd.read_excel(f)
            rows_seen = len(df)
            if 'ticker' not in df.columns:
                raise ValueError('missing ticker')
            for c in ['rating', 'setup', 'focus', 'key_level']:
                if c not in df.columns:
                    df[c] = None
            df['ticker'] = df['ticker'].astype(str).str.upper().str.strip()
            df = df[df['ticker'].str.len() > 0].drop_duplicates(['ticker'])
            for _, r in df.iterrows():
                exists = con.execute('select count(*) from watchlist_candidates where watchlist_date=? and ticker=? and source_file=?', [d, r['ticker'], f.name]).fetchone()[0]
                if exists:
                    continue
                cid = con.execute("select nextval('candidate_seq')").fetchone()[0]
                con.execute('insert into watchlist_candidates values (?, ?, ?, ?, ?, ?, ?, ?, ?)', [cid, d, r['ticker'], r['rating'], r['setup'], r['focus'], r['key_level'], f.name, datetime.now(timezone.utc)])
                rows_inserted += 1
                inserted += 1
        except Exception as err:
            failures.append(f'{f.name}: {err}')
        con.execute('insert into watchlist_files values (?, ?, ?, ?, ?, ?)', [f.name, h, d, rows_seen, rows_inserted, datetime.now(timezone.utc)])
    return {
        'files_scanned': len(files),
        'candidates_inserted': inserted,
        'skipped_sample_files': skipped_sample_files,
        'skipped_weekend_files': skipped_weekend_files,
        'failures': failures,
    }
