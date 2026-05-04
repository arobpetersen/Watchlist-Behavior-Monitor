from __future__ import annotations

import pandas as pd
import streamlit as st

from src.backwatch_source import (
    infer_setup_date,
    is_sample_or_test_file,
    list_source_files,
    normalize_backwatch_file,
    process_new_source_files,
    reprocess_source_file,
    resolve_source_dir,
    scan_source_files,
)
from src.config import get_settings
from src.data_maintenance import (
    find_orphaned_watchlist_sources,
    preview_watchlist_source_removal,
    remove_sample_data,
    remove_watchlist_source,
    watchlist_source_files,
)
from src.data_health import data_health_rows
from src.database import get_connection
from src.db_backup import create_db_backup
from src.run_daily import run_daily_pipeline
from src.watchlist_ingestion import ingest_watchlists


def _status_table(rows):
    return pd.DataFrame([
        {
            'File': r.source_file,
            'Setup Date': r.inferred_setup_date or '',
            'Tickers': '' if r.ticker_count is None else r.ticker_count,
            'Status': r.status,
            'Message': r.message,
        }
        for r in rows
    ])


def _summary_table(summary: dict):
    labels = [
        ('Source files scanned', 'source_files_scanned'),
        ('New files processed', 'new_files_processed'),
        ('Already processed files skipped', 'already_processed_files_skipped'),
        ('Sample/test files skipped', 'skipped_sample_files'),
        ('Reprocessed files', 'reprocessed_files'),
        ('Candidates removed', 'candidates_removed'),
        ('Files missing date', 'files_missing_date'),
        ('Files with no valid tickers', 'files_no_valid_tickers'),
        ('Candidates inserted', 'candidates_inserted'),
        ('Bars fetched', 'bars_fetched'),
        ('Daily bars fetched', 'daily_bars_fetched'),
        ('Features calculated', 'features_calculated'),
        ('Forward stats calculated', 'forward_stats_calculated'),
        ('Labels assigned', 'labels_assigned'),
        ('Failures', 'failures_count'),
    ]
    return pd.DataFrame([{'Metric': label, 'Value': summary.get(key, 0)} for label, key in labels])


st.set_page_config(page_title='Watchlist Behavior Monitor', layout='wide')

settings = get_settings()
source_dir = resolve_source_dir(settings.backwatch_source_dir, settings.project_root)
con = get_connection(str(settings.db_path))

st.title('Back-Watch Setup Behavior Monitor')

st.subheader('Back-Watch Source Folder')
st.write(f'Configured Back-Watch source folder: `{source_dir}`')
st.write(f'Canonical internal folder: `{settings.watchlists_dir}`')

if not source_dir.exists():
    st.warning('Configured Back-Watch source folder does not exist.')
    scanned = []
else:
    scanned = scan_source_files(source_dir, settings.watchlists_dir, con)

with st.expander('Data Health / Source Integrity'):
    health = data_health_rows(con, source_dir, settings.watchlists_dir)
    if health.empty:
        st.info('No setup source files or database candidates found yet.')
    else:
        st.dataframe(health, width='stretch', hide_index=True)

st.subheader('Daily Workflow')
if st.button('Process All New Back-Watch Files', type='primary'):
    if not source_dir.exists():
        st.warning('Configured Back-Watch source folder does not exist.')
    else:
        with st.spinner('Processing Back-Watch source files...'):
            processed_rows, saved_paths = process_new_source_files(source_dir, settings.watchlists_dir, con)
            ingest_result = ingest_watchlists(con, settings.watchlists_dir)
            con.close()

        pipeline_summary = {}
        metrics_message = ''
        if not settings.massive_api_key:
            metrics_message = 'API key missing — files were ingested but metrics were not updated.'
            st.warning(metrics_message)
        else:
            with st.spinner('Running metrics pipeline...'):
                pipeline_summary = run_daily_pipeline()
            st.success('Back-Watch processing complete.')

        failures = [
            r.message for r in processed_rows if r.status == 'Error'
        ] + ingest_result['failures'] + pipeline_summary.get('failures', [])

        summary = {
            'source_files_scanned': len(processed_rows),
            'new_files_processed': sum(1 for r in processed_rows if r.status == 'Processed'),
            'already_processed_files_skipped': sum(1 for r in processed_rows if r.status == 'Already Processed'),
            'skipped_sample_files': sum(1 for r in processed_rows if r.status == 'Skipped Sample/Test') + ingest_result.get('skipped_sample_files', 0),
            'reprocessed_files': 0,
            'candidates_removed': 0,
            'files_missing_date': sum(1 for r in processed_rows if r.status == 'Missing Date'),
            'files_no_valid_tickers': sum(1 for r in processed_rows if r.status == 'No Valid Tickers'),
            'candidates_inserted': ingest_result['candidates_inserted'],
            'bars_fetched': pipeline_summary.get('bars_fetched', 0),
            'daily_bars_fetched': pipeline_summary.get('daily_bars_fetched', 0),
            'features_calculated': pipeline_summary.get('features_calculated', 0),
            'forward_stats_calculated': pipeline_summary.get('forward_stats_calculated', 0),
            'labels_assigned': pipeline_summary.get('labels_assigned', 0),
            'failures_count': len(failures),
        }

        st.dataframe(_summary_table(summary), width='stretch', hide_index=True)
        st.dataframe(_status_table(processed_rows), width='stretch', hide_index=True)
        if saved_paths:
            st.write(f'Canonical files saved: {len(saved_paths)}')
        if failures:
            st.warning('Failures')
            st.write(failures)
        if metrics_message:
            st.info(metrics_message)

with st.expander('Maintenance / Reprocess'):
    if st.button('Create DB Backup'):
        try:
            backup = create_db_backup(settings.db_path, settings.project_root / 'data' / 'exports')
            st.success(f'DB backup created: `{backup}`')
        except Exception as exc:
            st.error(f'DB backup failed: {exc}')

    if st.button('Remove Sample/Test Rows From Live Tables'):
        cleanup = remove_sample_data(con)
        st.success('Sample/test cleanup complete.')
        st.dataframe(pd.DataFrame([cleanup]), width='stretch', hide_index=True)

    with st.expander('Source File Cleanup', expanded=False):
        st.caption('Remove imported candidates for one selected source file. Cached market bars are not deleted.')
        orphan_check_folder = source_dir if source_dir.exists() else settings.watchlists_dir
        orphaned_sources = find_orphaned_watchlist_sources(con, orphan_check_folder)
        if orphaned_sources.empty:
            st.info('No orphaned imported source files found in the configured source folder.')
        else:
            st.write('Orphaned imported source files')
            st.dataframe(orphaned_sources, width='stretch', hide_index=True)

        imported_sources = watchlist_source_files(con)
        if imported_sources:
            selected_cleanup_source = st.selectbox('Imported Source File', imported_sources, key='source_file_cleanup_source')
            cleanup_preview = preview_watchlist_source_removal(con, selected_cleanup_source)
            st.dataframe(pd.DataFrame([cleanup_preview]), width='stretch', hide_index=True)
            confirmed_cleanup = st.checkbox(
                'I understand this will remove candidates imported from the selected source file only.',
                key='source_file_cleanup_confirm',
            )
            if st.button('Remove Selected Source File Candidates', disabled=not confirmed_cleanup):
                cleanup = remove_watchlist_source(con, selected_cleanup_source)
                st.cache_data.clear()
                st.success('Selected source file candidates removed.')
                st.dataframe(pd.DataFrame([cleanup]), width='stretch', hide_index=True)
        else:
            st.info('No imported source files are available for cleanup.')

    files = list_source_files(source_dir) if source_dir.exists() else []
    real_files = [f for f in files if not is_sample_or_test_file(f.name) and infer_setup_date(f.name)]
    if real_files:
        labels = [f.name for f in real_files]
        selected_name = st.selectbox('Back-Watch Source File', labels)
        selected = real_files[labels.index(selected_name)]
        try:
            preview = normalize_backwatch_file(selected.path)
            st.write(f'Setup date: `{infer_setup_date(selected.name)}`')
            st.write(f'Tickers detected: {len(preview)}')
        except Exception as exc:
            preview = pd.DataFrame()
            st.warning(f'Could not preview selected file: {exc}')

        if st.button('Reprocess Selected Back-Watch File'):
            with st.spinner('Reprocessing selected Back-Watch file...'):
                try:
                    reprocess_summary = reprocess_source_file(con, selected.path, settings.watchlists_dir)
                    con.close()
                    pipeline_summary = {}
                    if settings.massive_api_key:
                        pipeline_summary = run_daily_pipeline()
                    else:
                        reprocess_summary['failures'].append('API key missing; file was reprocessed but metrics were not updated.')
                    st.success('Selected Back-Watch file reprocessed.')
                    st.dataframe(pd.DataFrame([{
                        'Selected File': reprocess_summary['source_file'],
                        'Setup Date': reprocess_summary['setup_date'],
                        'Old Candidates Removed': reprocess_summary['old_candidates_removed'],
                        'New Candidates Inserted': reprocess_summary['new_candidates_inserted'],
                        'Features Calculated': pipeline_summary.get('features_calculated', 0),
                        'Labels Assigned': pipeline_summary.get('labels_assigned', 0),
                        'Failures': len(reprocess_summary['failures']) + len(pipeline_summary.get('failures', [])),
                    }]), width='stretch', hide_index=True)
                    failures = reprocess_summary['failures'] + pipeline_summary.get('failures', [])
                    if failures:
                        st.warning('Failures')
                        st.write(failures)
                except Exception as exc:
                    st.error(f'Reprocess failed: {exc}')

        if st.button('Reprocess All Source Files'):
            summaries, failures = [], []
            with st.spinner('Reprocessing all Back-Watch source files...'):
                for source in real_files:
                    try:
                        summaries.append(reprocess_source_file(con, source.path, settings.watchlists_dir))
                    except Exception as exc:
                        failures.append(f'{source.name}: {exc}')
                con.close()
                pipeline_summary = {}
                if settings.massive_api_key:
                    pipeline_summary = run_daily_pipeline()
                else:
                    failures.append('API key missing; files were reprocessed but metrics were not updated.')
            st.success('All Back-Watch source files reprocessed.')
            st.dataframe(_summary_table({
                'source_files_scanned': len(files),
                'new_files_processed': 0,
                'already_processed_files_skipped': 0,
                'skipped_sample_files': sum(1 for f in files if is_sample_or_test_file(f.name)),
                'reprocessed_files': len(summaries),
                'candidates_removed': sum(s['old_candidates_removed'] for s in summaries),
                'candidates_inserted': sum(s['new_candidates_inserted'] for s in summaries),
                'features_calculated': pipeline_summary.get('features_calculated', 0),
                'labels_assigned': pipeline_summary.get('labels_assigned', 0),
                'failures_count': len(failures) + len(pipeline_summary.get('failures', [])),
            }), width='stretch', hide_index=True)
            all_failures = failures + pipeline_summary.get('failures', [])
            if all_failures:
                st.warning('Failures')
                st.write(all_failures)
    else:
        st.info('No real Back-Watch source files are available to reprocess.')

st.subheader('Source Files')
if source_dir.exists():
    if scanned:
        st.dataframe(_status_table(scanned), width='stretch', hide_index=True)
        files = list_source_files(source_dir)
        labels = [f.name for f in files]
        with st.expander('Preview Source File'):
            selected_name = st.selectbox('Source File', labels)
            selected = files[labels.index(selected_name)]
            try:
                preview = normalize_backwatch_file(selected.path)
                st.write(f'Tickers detected: {len(preview)}')
                st.dataframe(preview, width='stretch', hide_index=True)
            except Exception as exc:
                st.warning(f'Could not preview selected file: {exc}')
    else:
        st.info('No CSV/XLSX/XLS files found in the configured source folder.')
