import streamlit as st

st.set_page_config(page_title='Back-Watch Setup Behavior Monitor', layout='wide')
st.title('Back-Watch Setup Behavior Monitor')
st.write('Use the Ingest Back-Watch page to pull a daily CSV/XLSX file from the configured source folder into the canonical `data/watchlists` folder.')
st.write('Recommended filename: `YYYY-MM-DD_backwatch.xlsx`. After ingesting, run `python -m src.run_daily` to update setup behavior metrics.')
