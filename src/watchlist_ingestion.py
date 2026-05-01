from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path

import pandas as pd


def infer_date(name: str) -> str | None:
    m = re.search(r'(\d{4}-\d{2}-\d{2})', name)
    return m.group(1) if m else None


def ingest_watchlists(con, watchlists_dir: Path) -> dict:
    files = sorted([*watchlists_dir.glob('*.csv'), *watchlists_dir.glob('*.xlsx')])
    inserted, failures = 0, []
    for f in files:
        rows_seen, rows_inserted = 0, 0
        d = infer_date(f.name)
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
                con.execute('insert into watchlist_candidates values (?, ?, ?, ?, ?, ?, ?, ?, ?)', [cid, d, r['ticker'], r['rating'], r['setup'], r['focus'], r['key_level'], f.name, datetime.utcnow()])
                rows_inserted += 1
                inserted += 1
        except Exception as err:
            failures.append(f'{f.name}: {err}')
        con.execute('insert into watchlist_files values (?, ?, ?, ?, ?, ?)', [f.name, h, d, rows_seen, rows_inserted, datetime.utcnow()])
    return {'files_scanned': len(files), 'candidates_inserted': inserted, 'failures': failures}
