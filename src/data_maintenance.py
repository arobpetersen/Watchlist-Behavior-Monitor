from __future__ import annotations

import argparse

from src.config import get_settings
from src.database import get_connection


SAMPLE_SQL = "lower(source_file) like '%sample%' or lower(source_file) like '%example%' or lower(source_file) like '%test%'"


def _count(con, sql: str, params: list | None = None) -> int:
    return int(con.execute(sql, params or []).fetchone()[0])


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
