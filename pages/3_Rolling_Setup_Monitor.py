import streamlit as st

from src.config import get_settings
from src.database import get_connection
from src.rolling_setup_monitor import (
    MAIN_COLUMNS,
    apply_setup_rating_updates,
    detail_table,
    main_table,
    rating_dropdown_options,
    rolling_setup_monitor,
    setup_dropdown_options,
)

st.set_page_config(page_title='Watchlist Behavior Monitor', layout='wide')

con = get_connection(str(get_settings().db_path))
st.title('Rolling Setup Monitor')

sections = rolling_setup_monitor(con, setup_dates=5)
if not sections:
    st.info('No setup candidates yet.')
else:
    for section in sections:
        st.subheader(f"Setup Date: {section['setup_date']}")

        summary = section['summary']
        cards = [
            'Setups',
            'Clean 1m',
            'Clean 5m',
            '1m Failed',
            '5m Failed',
            'Alt Required',
            'No Trigger',
            'Active',
            'Failed',
            'Retested',
            'Median Current %',
            'Median Max %',
        ]
        for start in range(0, len(cards), 6):
            cols = st.columns(6)
            for col, label in zip(cols, cards[start:start + 6]):
                col.metric(label, summary[label])

        table = section['table']
        display = main_table(table)
        editable = display.copy()
        editable.insert(0, 'candidate_id', table['candidate_id'].tolist())

        edited = st.data_editor(
            editable,
            key=f"monitor_editor_{section['setup_date']}",
            width='stretch',
            hide_index=True,
            column_order=MAIN_COLUMNS,
            disabled=[c for c in editable.columns if c not in {'Setup', 'Rating'}],
            column_config={
                'Setup': st.column_config.SelectboxColumn(
                    'Setup',
                    options=setup_dropdown_options(table),
                ),
                'Rating': st.column_config.SelectboxColumn(
                    'Rating',
                    options=rating_dropdown_options(table),
                ),
            },
        )

        if st.button('Save Setup/Rating', key=f"save_monitor_{section['setup_date']}"):
            edited_for_save = edited.copy()
            edited_for_save['candidate_id'] = editable['candidate_id'].tolist()
            changed = apply_setup_rating_updates(con, editable, edited_for_save)
            if changed:
                st.success(f'Saved Setup/Rating for {changed} row(s).')
                st.rerun()
            else:
                st.info('No Setup/Rating changes to save.')

        with st.expander('Show full detail table', expanded=False):
            st.dataframe(detail_table(table), width='stretch', hide_index=True)
