from __future__ import annotations

import json


def assign_label(row: dict):
    or1 = json.loads(row.get('or_1m') or '{}')
    or5 = json.loads(row.get('or_5m') or '{}')
    primary = 'Mixed / Watch Only'
    if or1.get('broke_orh') and not or1.get('orh_then_orl') and or1.get('closed_above_orh'):
        primary = 'Clean 1m ORH Trend'
    elif or5.get('broke_orh') and not or5.get('orh_then_orl') and or5.get('closed_above_orh'):
        primary = 'Clean 5m ORH Trend'
    elif or1.get('orh_then_orl'):
        primary = '1m ORH Fakeout'
    elif or5.get('orh_then_orl'):
        primary = '5m ORH Fakeout'
    elif or5.get('orl_then_orh'):
        primary = 'ORL Shakeout Then Higher'
    sec = []
    if row.get('close_location', 0) >= 0.8:
        sec.append('Closed Strong')
    if row.get('close_location', 1) <= 0.3:
        sec.append('Closed Weak')
    return primary, ', '.join(sec), ''


def assign_labels_for_date(con, d: str) -> int:
    df = con.execute('select * from entry_day_features where watchlist_date=?', [d]).df()
    n = 0
    for _, r in df.iterrows():
        p, s, reason = assign_label(r.to_dict())
        con.execute('delete from behavior_labels where candidate_id=?', [int(r['candidate_id'])])
        con.execute('insert into behavior_labels values (?, ?, ?, ?, ?, ?)', [int(r['candidate_id']), d, r['ticker'], p, s, reason])
        n += 1
    return n
