from __future__ import annotations

import json


def _or_result(s: str) -> str:
    if not isinstance(s, str):
        return 'No Break'
    d = json.loads(s or '{}')
    if not d:
        return 'No Break'
    up, dn = d.get('broke_orh'), d.get('broke_orl')
    if up and dn:
        return 'Failed' if d.get('orh_then_orl') else 'Both Sides'
    if up and d.get('closed_above_orh'):
        return 'Held'
    if up:
        return 'Broke High Only'
    if dn and d.get('closed_below_orl'):
        return 'Failed'
    if dn:
        return 'Broke Low Only'
    return 'No Break'


def dates(con):
    return [r[0] for r in con.execute('select distinct watchlist_date from watchlist_candidates where watchlist_date is not null order by watchlist_date desc').fetchall()]


def snapshot_metrics(con, d):
    return con.execute("""
    select count(*) as names,
    avg(case when closed_near_high then 1 else 0 end) as pct_closed_near_high,
    avg(case when closed_above_vwap then 1 else 0 end) as pct_closed_above_vwap,
    avg(case when json_extract(or_1m,'$.broke_orh')::boolean then 1 else 0 end) as pct_broke_1m_orh,
    avg(case when json_extract(or_1m,'$.orh_then_orl')::boolean then 1 else 0 end) as pct_1m_fakeout,
    avg(case when json_extract(or_5m,'$.broke_orh')::boolean then 1 else 0 end) as pct_broke_5m_orh,
    avg(case when json_extract(or_5m,'$.orh_then_orl')::boolean then 1 else 0 end) as pct_5m_fakeout,
    median(close_location) as median_close_location,
    median(range_vs_atr20) as median_range_vs_atr20,
    median(relative_volume_20d) as median_relative_volume_20d,
    avg(case when broke_entry_day_high_within_3d then 1 else 0 end) as pct_broke_entry_day_high_within_3d,
    avg(case when broke_entry_day_low_within_3d then 1 else 0 end) as pct_broke_entry_day_low_within_3d
    from entry_day_features where watchlist_date=?
    """, [d]).df().iloc[0].to_dict()


def snapshot_table(con, d):
    df = con.execute('''
    select c.ticker,c.rating,c.setup,c.focus,b.primary_label,b.secondary_labels,
           f.close_location,f.closed_above_vwap,f.gap_pct,f.range_vs_atr20,
           f.relative_volume_20d,f.broke_entry_day_high_within_3d,
           f.broke_entry_day_low_within_3d,f.or_1m,f.or_5m,f.or_15m
    from watchlist_candidates c
    left join entry_day_features f using(candidate_id,watchlist_date,ticker)
    left join behavior_labels b using(candidate_id,watchlist_date,ticker)
    where c.watchlist_date=? order by c.ticker''', [d]).df()
    df['1m OR result'] = df['or_1m'].apply(_or_result)
    df['5m OR result'] = df['or_5m'].apply(_or_result)
    df['15m OR result'] = df['or_15m'].apply(_or_result)
    return df[['ticker','rating','setup','focus','primary_label','secondary_labels','close_location','closed_above_vwap','gap_pct','range_vs_atr20','relative_volume_20d','broke_entry_day_high_within_3d','broke_entry_day_low_within_3d','1m OR result','5m OR result','15m OR result']]
