from __future__ import annotations

from datetime import date

import streamlit as st

from src.backwatch_source import (
    infer_setup_date,
    list_source_files,
    normalize_backwatch_file,
    resolve_source_dir,
    save_canonical_watchlist,
)
from src.config import get_settings
from src.database import get_connection
from src.watchlist_ingestion import ingest_watchlists


settings = get_settings()
source_dir = resolve_source_dir(settings.backwatch_source_dir, settings.project_root)

st.title('Ingest Back-Watch File')
st.write(f'Configured source folder: `{source_dir}`')
st.write(f'Canonical internal folder: `{settings.watchlists_dir}`')

if not source_dir.exists():
    st.warning('Configured Back-Watch source folder does not exist.')
else:
    files = list_source_files(source_dir)
    if not files:
        st.info('No CSV/XLSX/XLS files found in the configured source folder.')
    else:
        labels = [f'{f.name} | {f.modified_at:%Y-%m-%d %H:%M} | {f.size:,} bytes' for f in files]
        selected_label = st.selectbox('Source File', labels)
        selected = files[labels.index(selected_label)]
        setup_date = infer_setup_date(selected.name)

        st.write(f'Selected path: `{selected.path}`')
        st.write(f'Modified: {selected.modified_at:%Y-%m-%d %H:%M:%S}')
        st.write(f'Size: {selected.size:,} bytes')

        if setup_date:
            st.success(f'Setup date inferred from filename: {setup_date}')
            final_date = setup_date
        else:
            st.warning('Could not infer setup date from filename. Choose the setup date manually.')
            final_date = st.date_input('Setup Date', value=date.today()).isoformat()

        try:
            preview = normalize_backwatch_file(selected.path)
            st.write(f'Tickers detected: {len(preview)}')
            st.dataframe(preview, use_container_width=True)
        except Exception as exc:
            preview = None
            st.error(f'Could not parse selected file: {exc}')

        if preview is not None and st.button('Ingest Selected Back-Watch File'):
            output_path, normalized = save_canonical_watchlist(selected.path, final_date, settings.watchlists_dir)
            con = get_connection(str(settings.db_path))
            result = ingest_watchlists(con, settings.watchlists_dir)
            st.success(f'Saved canonical file: {output_path.name}')
            st.write(f'Normalized rows: {len(normalized)}')
            st.write(f"Candidates inserted: {result['candidates_inserted']}")
            if result['failures']:
                st.warning('Some files reported ingestion warnings.')
                st.write(result['failures'])

        st.info('Run Daily Pipeline: `python -m src.run_daily`')
