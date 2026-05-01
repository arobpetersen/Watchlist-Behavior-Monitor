from __future__ import annotations

import pandas as pd
import streamlit as st

from src.backwatch_source import (
    list_source_files,
    normalize_backwatch_file,
    process_new_source_files,
    resolve_source_dir,
    scan_source_files,
)
from src.config import get_settings
from src.database import get_connection
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

        st.dataframe(_summary_table(summary), use_container_width=True, hide_index=True)
        st.dataframe(_status_table(processed_rows), use_container_width=True, hide_index=True)
        if saved_paths:
            st.write(f'Canonical files saved: {len(saved_paths)}')
        if failures:
            st.warning('Failures')
            st.write(failures)
        if metrics_message:
            st.info(metrics_message)

st.subheader('Source Files')
if source_dir.exists():
    if scanned:
        st.dataframe(_status_table(scanned), use_container_width=True, hide_index=True)
        files = list_source_files(source_dir)
        labels = [f.name for f in files]
        with st.expander('Preview Source File'):
            selected_name = st.selectbox('Source File', labels)
            selected = files[labels.index(selected_name)]
            try:
                preview = normalize_backwatch_file(selected.path)
                st.write(f'Tickers detected: {len(preview)}')
                st.dataframe(preview, use_container_width=True, hide_index=True)
            except Exception as exc:
                st.warning(f'Could not preview selected file: {exc}')
    else:
        st.info('No CSV/XLSX/XLS files found in the configured source folder.')
