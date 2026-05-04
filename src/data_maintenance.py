from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.config import get_settings
from src.database import get_connection


SAMPLE_SQL = "lower(source_file) like '%sample%' or lower(source_file) like '%example%' or lower(source_file) like '%test%'"


def _count(con, sql: str, params: list | None = None) -> int:
    return int(con.execute(sql, params or []).fetchone()[0])


def _stringify(value) -> str:
    if value is None:
        return ''
    return str(value)


def watchlist_source_files(con) -> list[str]:
    rows = con.execute(
        '''
        select source_file
        from (
            select distinct source_file from watchlist_candidates where source_file is not null
            union
            select distinct source_file from watchlist_files where source_file is not null
        )
        order by source_file desc
        '''
    ).fetchall()
    return [row[0] for row in rows]


def preview_watchlist_source_removal(con, source_file: str) -> dict:
    candidate_stats = con.execute(
        '''
        select
            count(*) as candidate_rows,
            count(distinct ticker) as distinct_tickers,
            min(watchlist_date) as watchlist_date_min,
            max(watchlist_date) as watchlist_date_max,
            min(ingested_at) as candidate_imported_at_min,
            max(ingested_at) as candidate_imported_at_max
        from watchlist_candidates
        where source_file=?
        ''',
        [source_file],
    ).fetchone()
    ledger_stats = con.execute(
        '''
        select
            count(*) as ledger_rows,
            min(watchlist_date) as ledger_watchlist_date_min,
            max(watchlist_date) as ledger_watchlist_date_max,
            min(ingested_at) as ledger_imported_at_min,
            max(ingested_at) as ledger_imported_at_max
        from watchlist_files
        where source_file=?
        ''',
        [source_file],
    ).fetchone()
    sample_tickers = [
        row[0]
        for row in con.execute(
            '''
            select distinct ticker
            from watchlist_candidates
            where source_file=?
            order by ticker
            limit 10
            ''',
            [source_file],
        ).fetchall()
    ]
    features = _count(
        con,
        '''
        select count(*)
        from entry_day_features
        where candidate_id in (
            select candidate_id from watchlist_candidates where source_file=?
        )
        ''',
        [source_file],
    )
    labels = _count(
        con,
        '''
        select count(*)
        from behavior_labels
        where candidate_id in (
            select candidate_id from watchlist_candidates where source_file=?
        )
        ''',
        [source_file],
    )

    return {
        'source_file': source_file,
        'candidate_rows': int(candidate_stats[0] or 0),
        'distinct_tickers': int(candidate_stats[1] or 0),
        'watchlist_date_min': _stringify(candidate_stats[2]),
        'watchlist_date_max': _stringify(candidate_stats[3]),
        'candidate_imported_at_min': _stringify(candidate_stats[4]),
        'candidate_imported_at_max': _stringify(candidate_stats[5]),
        'sample_tickers': ', '.join(sample_tickers),
        'entry_day_features_rows': features,
        'behavior_labels_rows': labels,
        'watchlist_file_rows': int(ledger_stats[0] or 0),
        'ledger_watchlist_date_min': _stringify(ledger_stats[1]),
        'ledger_watchlist_date_max': _stringify(ledger_stats[2]),
        'ledger_imported_at_min': _stringify(ledger_stats[3]),
        'ledger_imported_at_max': _stringify(ledger_stats[4]),
    }


def find_orphaned_watchlist_sources(con, watchlist_folder_path=None) -> pd.DataFrame:
    sources = watchlist_source_files(con)
    if not sources or not watchlist_folder_path:
        return pd.DataFrame(columns=['source_file', 'candidate_rows', 'distinct_tickers', 'watchlist_date_min', 'watchlist_date_max'])

    folder = Path(watchlist_folder_path)
    if not folder.exists():
        existing_files: set[str] = set()
    else:
        existing_files = {path.name for path in folder.iterdir() if path.is_file()}

    rows = []
    for source_file in sources:
        if source_file in existing_files:
            continue
        preview = preview_watchlist_source_removal(con, source_file)
        rows.append({
            'source_file': source_file,
            'candidate_rows': preview['candidate_rows'],
            'distinct_tickers': preview['distinct_tickers'],
            'watchlist_date_min': preview['watchlist_date_min'],
            'watchlist_date_max': preview['watchlist_date_max'],
            'sample_tickers': preview['sample_tickers'],
        })
    return pd.DataFrame(rows)


def remove_watchlist_source(con, source_file: str) -> dict:
    preview = preview_watchlist_source_removal(con, source_file)
    con.execute(
        '''
        delete from behavior_labels
        where candidate_id in (
            select candidate_id from watchlist_candidates where source_file=?
        )
        ''',
        [source_file],
    )
    con.execute(
        '''
        delete from entry_day_features
        where candidate_id in (
            select candidate_id from watchlist_candidates where source_file=?
        )
        ''',
        [source_file],
    )
    con.execute('delete from watchlist_candidates where source_file=?', [source_file])
    con.execute('delete from watchlist_files where source_file=?', [source_file])

    return {
        'source_file': source_file,
        'candidates_removed': preview['candidate_rows'],
        'features_removed': preview['entry_day_features_rows'],
        'labels_removed': preview['behavior_labels_rows'],
        'watchlist_file_rows_removed': preview['watchlist_file_rows'],
    }


def remove_candidates_for_source(con, setup_date: str, source_file: str) -> dict:
    params = [setup_date, source_file]
    candidate_filter = 'watchlist_date=? and source_file=?'
    candidates = _count(con, f'select count(*) from watchlist_candidates where {candidate_filter}', params)
    features = _count(
        con,
        f'''
        select count(*)
        from entry_day_features
        where candidate_id in (
            select candidate_id from watchlist_candidates where {candidate_filter}
        )
        ''',
        params,
    )
    labels = _count(
        con,
        f'''
        select count(*)
        from behavior_labels
        where candidate_id in (
            select candidate_id from watchlist_candidates where {candidate_filter}
        )
        ''',
        params,
    )
    watchlist_file_rows = _count(con, 'select count(*) from watchlist_files where watchlist_date=? and source_file=?', params)

    con.execute(
        f'''
        delete from behavior_labels
        where candidate_id in (
            select candidate_id from watchlist_candidates where {candidate_filter}
        )
        ''',
        params,
    )
    con.execute(
        f'''
        delete from entry_day_features
        where candidate_id in (
            select candidate_id from watchlist_candidates where {candidate_filter}
        )
        ''',
        params,
    )
    con.execute(f'delete from watchlist_candidates where {candidate_filter}', params)
    con.execute('delete from watchlist_files where watchlist_date=? and source_file=?', params)

    return {
        'candidates_removed': candidates,
        'features_removed': features,
        'labels_removed': labels,
        'watchlist_file_rows_removed': watchlist_file_rows,
    }


def remove_sample_data(con) -> dict:
    candidates = _count(con, f'select count(*) from watchlist_candidates where {SAMPLE_SQL}')
    features = _count(
        con,
        f'''
        select count(*)
        from entry_day_features
        where candidate_id in (
            select candidate_id from watchlist_candidates where {SAMPLE_SQL}
        )
        ''',
    )
    labels = _count(
        con,
        f'''
        select count(*)
        from behavior_labels
        where candidate_id in (
            select candidate_id from watchlist_candidates where {SAMPLE_SQL}
        )
        ''',
    )
    watchlist_file_rows = _count(con, f'select count(*) from watchlist_files where {SAMPLE_SQL}')

    con.execute(
        f'''
        delete from behavior_labels
        where candidate_id in (
            select candidate_id from watchlist_candidates where {SAMPLE_SQL}
        )
        '''
    )
    con.execute(
        f'''
        delete from entry_day_features
        where candidate_id in (
            select candidate_id from watchlist_candidates where {SAMPLE_SQL}
        )
        '''
    )
    con.execute(f'delete from watchlist_candidates where {SAMPLE_SQL}')
    con.execute(f'delete from watchlist_files where {SAMPLE_SQL}')
    return {
        'candidates_removed': candidates,
        'features_removed': features,
        'labels_removed': labels,
        'watchlist_file_rows_removed': watchlist_file_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--remove-samples', action='store_true')
    args = parser.parse_args()
    settings = get_settings()
    con = get_connection(str(settings.db_path))
    if args.remove_samples:
        summary = remove_sample_data(con)
        print('Sample data cleanup')
        for key, value in summary.items():
            print(f'- {key}: {value}')
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
