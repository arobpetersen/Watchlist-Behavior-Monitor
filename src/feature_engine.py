from __future__ import annotations

import json
from datetime import datetime, timedelta

import pandas as pd

from src.daily_context import calculate_daily_context


def session_filter(df: pd.DataFrame) -> pd.DataFrame:
    t = df['timestamp_et'].dt.time
    return df[(t >= pd.Timestamp('09:30').time()) & (t <= pd.Timestamp('16:00').time())].copy()


def calc_vwap(df: pd.DataFrame) -> pd.Series:
    tp = (df['high'] + df['low'] + df['close']) / 3
    return (tp * df['volume']).cumsum() / df['volume'].cumsum().replace(0, pd.NA)


def opening_range(df: pd.DataFrame, minutes: int) -> dict:
    start = df['timestamp_et'].min().replace(hour=9, minute=30, second=0)
    end = start + timedelta(minutes=minutes)
    w = df[(df['timestamp_et'] >= start) & (df['timestamp_et'] < end)]
    if w.empty:
        return {}
    orh, orl = float(w['high'].max()), float(w['low'].min())
    post = df[df['timestamp_et'] >= end]
    up = post[post['high'] > orh]
    dn = post[post['low'] < orl]
    ut = None if up.empty else up.iloc[0]['timestamp_et']
    dt = None if dn.empty else dn.iloc[0]['timestamp_et']
    same_bar_break = ut is not None and dt is not None and ut == dt
    first = 'up' if ut is not None and (dt is None or ut < dt) else 'down' if dt is not None and (ut is None or dt < ut) else 'none'
    rec = {'orh':orh,'orl':orl,'orh_break_time':str(ut) if ut is not None else None,'orl_break_time':str(dt) if dt is not None else None,'broke_orh':ut is not None,'broke_orl':dt is not None,'first_break_direction':first,'orh_then_orl':ut is not None and dt is not None and ut < dt,'orl_then_orh':ut is not None and dt is not None and dt < ut,'same_bar_orh_orl_break':same_bar_break,'closed_above_orh':float(df.iloc[-1]['close'])>orh,'closed_below_orl':float(df.iloc[-1]['close'])<orl}
    if ut is not None:
        aft = post[post['timestamp_et'] >= ut]
        rec['max_gain_after_orh_break_pct'] = float((aft['high'].max()-orh)/orh)
        rec['max_drawdown_after_orh_break_pct'] = float((aft['low'].min()-orh)/orh)
    else:
        rec['max_gain_after_orh_break_pct'] = None
        rec['max_drawdown_after_orh_break_pct'] = None
    return rec


def compute_features(con, candidate: dict) -> bool:
    df = con.execute('select * from intraday_bars_1m where ticker=? and trading_date=? order by timestamp_et', [candidate['ticker'], str(candidate['watchlist_date'])]).df()
    if df.empty:
        return False
    df['timestamp_et'] = pd.to_datetime(df['timestamp_et'])
    df = session_filter(df)
    if df.empty:
        return False
    df['vwap'] = calc_vwap(df)
    high, low, close = float(df['high'].max()), float(df['low'].min()), float(df.iloc[-1]['close'])
    daily_df = con.execute('select * from daily_bars where ticker=? order by trading_date', [candidate['ticker']]).df()
    daily_context = calculate_daily_context(daily_df, candidate['ticker'], str(candidate['watchlist_date']))
    rec = {
        'candidate_id':candidate['candidate_id'],'watchlist_date':str(candidate['watchlist_date']),'ticker':candidate['ticker'],
        'open_price':float(df.iloc[0]['open']),'high_price':high,'low_price':low,'close_price':close,
        'hod_time':str(df.loc[df['high'].idxmax(),'timestamp_et']),'lod_time':str(df.loc[df['low'].idxmin(),'timestamp_et']),
        'close_location':(close-low)/max(high-low,1e-9),'closed_near_high':(close-low)/max(high-low,1e-9)>=0.8,'closed_near_low':(close-low)/max(high-low,1e-9)<=0.2,
        'session_vwap':float(df['vwap'].iloc[-1]),'closed_above_vwap':close>float(df['vwap'].iloc[-1]),'ever_below_vwap':bool((df['low']<df['vwap']).any()),'ever_above_vwap':bool((df['high']>df['vwap']).any()),
        'lost_vwap':False,'reclaimed_vwap':False,'vwap_reclaim_then_new_hod':False,
        'or_1m':json.dumps(opening_range(df,1)),'or_5m':json.dumps(opening_range(df,5)),'or_15m':json.dumps(opening_range(df,15)),'calculated_at':datetime.utcnow()
    }
    rec.update(daily_context)
    cols=list(rec.keys())
    con.execute('delete from entry_day_features where candidate_id=?',[candidate['candidate_id']])
    con.execute(f"insert into entry_day_features ({','.join(cols)}) values ({','.join(['?']*len(cols))})", list(rec.values()))
    return True
