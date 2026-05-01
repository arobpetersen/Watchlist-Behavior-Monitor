from __future__ import annotations

import json
from typing import Any

import pandas as pd

from src.dashboard_queries import _clean_display_df, _close_bucket, _or_result


TRIGGER_PREFIXES = {
    'Clean 1m ORH': '[Clean] Clean 1m ORH',
    'Clean 5m ORH': '[Clean] Clean 5m ORH',
    'Alternate Means Required': '[Alt] Alternate Means Required',
    'No Clean OR Trigger': '[None] No Clean OR Trigger',
}

STATUS_PREFIXES = {
    'Trending Higher': '[Up] Trending Higher',
    'Still Working': '[Work] Still Working',
    'Pulled Back but Holding': '[Pullback] Pulled Back but Holding',
    'Failed Setup-Day Low': '[Fail] Failed Setup-Day Low',
    'No Clean OR Trigger': '[None] No Clean OR Trigger',
    'Unresolved': '[Open] Unresolved',
}

STATUS_PRIORITY = {
    'Trending Higher': 0,
    'Still Working': 1,
    'Pulled Back but Holding': 2,
    'Unresolved': 3,
    'No Clean OR Trigger': 4,
    'Failed Setup-Day Low': 5,
}

MONITOR_COLUMNS = [
    'Ticker',
    'OR Trigger',
    'Current Status',
    'Current vs Ref',
    'Current vs Setup Close',
    'Max Gain',
    'Setup Low Broke',
    'Setup High Broke',
    'Close Bucket',
    '1m OR',
    '5m OR',
    'RVOL',
    'Range / ATR',
    'Ref Price',
    'Reference',
    'Latest Close',
    'Rating',
    'Setup',
    'Focus',
]


def _loads(value: Any) -> dict:
    if not isinstance(value, str) or not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


def _pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)


def derive_trigger_reference(or_1m: str, or_5m: str, or_15m: str, close_location) -> dict:
    one = _loads(or_1m)
    five = _loads(or_5m)
    fifteen = _loads(or_15m)
    if one.get('broke_orh') and not one.get('orh_then_orl'):
        return {
            'trigger_reference_type': 'Clean 1m ORH',
            'trigger_reference_price': one.get('orh'),
            'trigger_reference_basis': '1m ORH',
        }
    if five.get('broke_orh') and not five.get('orh_then_orl'):
        return {
            'trigger_reference_type': 'Clean 5m ORH',
            'trigger_reference_price': five.get('orh'),
            'trigger_reference_basis': '5m ORH',
        }
    if (
        one.get('broke_orh')
        and one.get('broke_orl')
        and five.get('broke_orh')
        and five.get('broke_orl')
        and close_location is not None
        and not pd.isna(close_location)
        and float(close_location) >= 0.80
    ):
        return {
            'trigger_reference_type': 'Alternate Means Required',
            'trigger_reference_price': fifteen.get('orh'),
            'trigger_reference_basis': '15m ORH Reference',
        }
    return {
        'trigger_reference_type': 'No Clean OR Trigger',
        'trigger_reference_price': None,
        'trigger_reference_basis': 'Setup-Day Close fallback',
    }


def current_status(
    setup_day_low_broken_since_setup: bool,
    setup_day_high_broken_since_setup: bool,
    latest_close: float | None,
    setup_day_high: float | None,
    trigger_reference_price: float | None,
    trigger_reference_type: str,
) -> str:
    if setup_day_low_broken_since_setup:
        return 'Failed Setup-Day Low'
    if latest_close is None:
        return 'Unresolved'
    if setup_day_high_broken_since_setup and (
        (setup_day_high is not None and latest_close >= setup_day_high)
        or (trigger_reference_price is not None and latest_close >= trigger_reference_price)
    ):
        return 'Trending Higher'
    if trigger_reference_price is not None and latest_close >= trigger_reference_price:
        return 'Still Working'
    if trigger_reference_price is not None and latest_close < trigger_reference_price:
        return 'Pulled Back but Holding'
    if not setup_day_high_broken_since_setup and trigger_reference_price is None:
        return 'Unresolved'
    if trigger_reference_type == 'No Clean OR Trigger':
        return 'No Clean OR Trigger'
    return 'Unresolved'


def display_trigger(value: str) -> str:
    return TRIGGER_PREFIXES.get(value, value)


def display_status(value: str) -> str:
    return STATUS_PREFIXES.get(value, value)


def sort_monitor_rows(df: pd.DataFrame) -> pd.DataFrame:
    table = df.copy()
    table['_status_priority'] = table['Status'].map(STATUS_PRIORITY).fillna(99)
    table['_current_setup_sort'] = table['Current % from Setup Close'].fillna(float('-inf'))
    return table.sort_values(
        ['_status_priority', '_current_setup_sort', 'Ticker'],
        ascending=[True, False, True],
    ).drop(columns=['_status_priority', '_current_setup_sort'])


def _follow_through(row: dict, daily_bars: pd.DataFrame) -> dict:
    setup_date = pd.to_datetime(row['watchlist_date']).date()
    ticker_bars = daily_bars[daily_bars['ticker'] == row['ticker']].copy()
    if ticker_bars.empty:
        return {
            'latest_trading_date': None,
            'latest_close': None,
            'current_pct_from_trigger': None,
            'current_pct_from_setup_close': None,
            'max_gain_from_trigger': None,
            'max_gain_from_setup_close': None,
            'max_drawdown_from_setup_close': None,
            'setup_day_high_broken_since_setup': False,
            'setup_day_low_broken_since_setup': False,
            'days_since_setup': None,
        }
    ticker_bars['trading_date'] = pd.to_datetime(ticker_bars['trading_date']).dt.date
    ticker_bars = ticker_bars[ticker_bars['trading_date'] >= setup_date].sort_values('trading_date')
    if ticker_bars.empty:
        return {
            'latest_trading_date': None,
            'latest_close': None,
            'current_pct_from_trigger': None,
            'current_pct_from_setup_close': None,
            'max_gain_from_trigger': None,
            'max_gain_from_setup_close': None,
            'max_drawdown_from_setup_close': None,
            'setup_day_high_broken_since_setup': False,
            'setup_day_low_broken_since_setup': False,
            'days_since_setup': None,
        }

    latest = ticker_bars.iloc[-1]
    after_setup = ticker_bars[ticker_bars['trading_date'] > setup_date]
    latest_close = float(latest['close'])
    setup_close = row.get('close_price')
    setup_high = row.get('high_price')
    setup_low = row.get('low_price')
    trigger_price = row.get('trigger_reference_price')
    max_high = None if ticker_bars.empty else float(ticker_bars['high'].max())
    min_low = None if ticker_bars.empty else float(ticker_bars['low'].min())

    high_broken = bool(not after_setup.empty and setup_high is not None and (after_setup['high'] > float(setup_high)).any())
    low_broken = bool(not after_setup.empty and setup_low is not None and (after_setup['low'] < float(setup_low)).any())

    return {
        'latest_trading_date': latest['trading_date'],
        'latest_close': latest_close,
        'current_pct_from_trigger': _pct(latest_close - trigger_price, trigger_price) if trigger_price is not None else None,
        'current_pct_from_setup_close': _pct(latest_close - setup_close, setup_close),
        'max_gain_from_trigger': _pct(max_high - trigger_price, trigger_price) if trigger_price is not None else None,
        'max_gain_from_setup_close': _pct(max_high - setup_close, setup_close),
        'max_drawdown_from_setup_close': _pct(min_low - setup_close, setup_close),
        'setup_day_high_broken_since_setup': high_broken,
        'setup_day_low_broken_since_setup': low_broken,
        'days_since_setup': (latest['trading_date'] - setup_date).days,
    }


def _fmt_pct(value) -> str:
    return '' if value is None or pd.isna(value) else f'{float(value) * 100:.1f}%'


def _fmt_price(value) -> str:
    return '' if value is None or pd.isna(value) else f'{float(value):.2f}'


def _format_monitor_table(df: pd.DataFrame) -> pd.DataFrame:
    table = sort_monitor_rows(df)
    table['OR Trigger'] = table['Trigger Type'].apply(display_trigger)
    table['Current Status'] = table['Status'].apply(display_status)
    table = table.rename(columns={
        'Current % from Ref.': 'Current vs Ref',
        'Current % from Setup Close': 'Current vs Setup Close',
        'Max Gain from Setup Close': 'Max Gain',
        'Setup Low Broken': 'Setup Low Broke',
        'Setup High Broken': 'Setup High Broke',
        'Ref. Price': 'Ref Price',
        'Ref. Basis': 'Reference',
    })
    table = table[MONITOR_COLUMNS]
    for column in ['Ref Price', 'Latest Close', 'RVOL', 'Range / ATR']:
        if column in table.columns:
            table[column] = table[column].apply(_fmt_price)
    for column in ['Current vs Ref', 'Current vs Setup Close', 'Max Gain']:
        if column in table.columns:
            table[column] = table[column].apply(_fmt_pct)
    return _clean_display_df(table)


def _summary_for_date(df: pd.DataFrame, setup_date) -> dict:
    count = len(df)
    setup_date_display = pd.to_datetime(setup_date).date().isoformat()
    def count_pct(mask):
        n = int(mask.sum())
        return f'{n} / {n / count * 100:.0f}%' if count else '0 / 0%'

    return {
        'Setup Date': setup_date_display,
        'Candidate Count': count,
        'Clean 1m ORH': count_pct(df['Trigger Type'] == 'Clean 1m ORH'),
        'Clean 5m ORH': count_pct(df['Trigger Type'] == 'Clean 5m ORH'),
        'Alternate Means Required': count_pct(df['Trigger Type'] == 'Alternate Means Required'),
        'No Clean OR Trigger': count_pct(df['Trigger Type'] == 'No Clean OR Trigger'),
        'Trending Higher': count_pct(df['Status'] == 'Trending Higher'),
        'Failed Setup-Day Low': count_pct(df['Status'] == 'Failed Setup-Day Low'),
        'Median Current % from Setup Close': _fmt_pct(df['current_pct_from_setup_close_raw'].median()),
        'Median Max Gain from Setup Close': _fmt_pct(df['max_gain_from_setup_close_raw'].median()),
    }


def rolling_setup_monitor(con, setup_dates: int = 5) -> list[dict]:
    dates = [
        r[0]
        for r in con.execute(
            'select distinct watchlist_date from watchlist_candidates where watchlist_date is not null order by watchlist_date desc limit ?',
            [setup_dates],
        ).fetchall()
    ]
    if not dates:
        return []
    candidates = con.execute(
        f"""
        select c.candidate_id,c.watchlist_date,c.ticker,c.rating,c.setup,c.focus,
               f.high_price,f.low_price,f.close_price,f.close_location,
               f.or_1m,f.or_5m,f.or_15m,f.relative_volume_20d,f.range_vs_atr20
        from watchlist_candidates c
        left join entry_day_features f using(candidate_id,watchlist_date,ticker)
        where c.watchlist_date in ({','.join(['?'] * len(dates))})
        order by c.watchlist_date desc, c.ticker
        """,
        dates,
    ).df()
    tickers = candidates['ticker'].dropna().astype(str).unique().tolist()
    daily_bars = con.execute(
        f"select * from daily_bars where ticker in ({','.join(['?'] * len(tickers))}) order by ticker,trading_date",
        tickers,
    ).df() if tickers else pd.DataFrame()

    rows = []
    for _, item in candidates.iterrows():
        record = item.to_dict()
        trigger = derive_trigger_reference(record.get('or_1m'), record.get('or_5m'), record.get('or_15m'), record.get('close_location'))
        record.update(trigger)
        follow = _follow_through(record, daily_bars)
        record.update(follow)
        record['current_status'] = current_status(
            record['setup_day_low_broken_since_setup'],
            record['setup_day_high_broken_since_setup'],
            record['latest_close'],
            record.get('high_price'),
            record.get('trigger_reference_price'),
            record.get('trigger_reference_type'),
        )
        rows.append(record)

    raw = pd.DataFrame(rows)
    sections = []
    for setup_date, group in raw.groupby('watchlist_date', sort=False):
        display = pd.DataFrame({
            'Ticker': group['ticker'],
            'Rating': group['rating'],
            'Setup': group['setup'],
            'Focus': group['focus'],
            'Trigger Type': group['trigger_reference_type'],
            'Ref. Price': group['trigger_reference_price'],
            'Ref. Basis': group['trigger_reference_basis'],
            'Latest Close': group['latest_close'],
            'Current % from Ref.': group['current_pct_from_trigger'],
            'Current % from Setup Close': group['current_pct_from_setup_close'],
            'Max Gain from Setup Close': group['max_gain_from_setup_close'],
            'Setup High Broken': group['setup_day_high_broken_since_setup'],
            'Setup Low Broken': group['setup_day_low_broken_since_setup'],
            'Status': group['current_status'],
            'Close Bucket': group['close_location'].apply(_close_bucket),
            '1m OR': group['or_1m'].apply(_or_result),
            '5m OR': group['or_5m'].apply(_or_result),
            'RVOL': group['relative_volume_20d'],
            'Range / ATR': group['range_vs_atr20'],
            'current_pct_from_setup_close_raw': group['current_pct_from_setup_close'],
            'max_gain_from_setup_close_raw': group['max_gain_from_setup_close'],
        })
        summary = _summary_for_date(display, setup_date)
        display = display.drop(columns=['current_pct_from_setup_close_raw', 'max_gain_from_setup_close_raw'])
        sections.append({'setup_date': setup_date, 'summary': summary, 'table': _format_monitor_table(display)})
    return sections
