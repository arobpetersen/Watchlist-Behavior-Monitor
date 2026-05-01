from __future__ import annotations

from datetime import date, datetime
from urllib.parse import urljoin

import pandas as pd
import requests


def _format_aggregate_date(value: str | date | datetime) -> str:
    parsed = pd.to_datetime(value).date()
    formatted = parsed.isoformat()
    if ' ' in formatted:
        raise ValueError('Aggregate date must be formatted as YYYY-MM-DD')
    return formatted


class MassiveClient:
    def __init__(self, api_key: str | None, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')

    def _get(self, url: str, params: dict, ticker: str, date_label: str):
        try:
            r = requests.get(url, params=params, timeout=30)
        except requests.RequestException as exc:
            raise RuntimeError(f"Massive fetch failed for {ticker} {date_label}: {exc.__class__.__name__}") from None
        try:
            r.raise_for_status()
        except requests.HTTPError:
            reason = r.reason or 'HTTP error'
            raise RuntimeError(f"Massive fetch failed for {ticker} {date_label}: {r.status_code} {reason}") from None
        return r

    def fetch_intraday_1m(self, ticker: str, trading_date: str | date | datetime) -> pd.DataFrame:
        if not self.api_key:
            raise RuntimeError('API key missing')
        date_str = _format_aggregate_date(trading_date)
        url = urljoin(self.base_url + '/', f"v2/aggs/ticker/{ticker}/range/1/minute/{date_str}/{date_str}")
        r = self._get(url, {'adjusted':'true', 'sort':'asc', 'limit':50000, 'apiKey':self.api_key}, ticker, f"on {date_str}")
        rows = r.json().get('results', [])
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df['timestamp_et'] = pd.to_datetime(df['t'], unit='ms', utc=True).dt.tz_convert('America/New_York').dt.tz_localize(None)
        df = df.rename(columns={'o':'open','h':'high','l':'low','c':'close','v':'volume'})
        df['ticker'] = ticker
        df['trading_date'] = date_str
        df['source'] = 'massive'
        df['fetched_at'] = datetime.utcnow()
        return df[['ticker','trading_date','timestamp_et','open','high','low','close','volume','source','fetched_at']]

    def fetch_daily(self, ticker: str, from_date: str | date | datetime, to_date: str | date | datetime) -> pd.DataFrame:
        if not self.api_key:
            raise RuntimeError('API key missing')
        from_str = _format_aggregate_date(from_date)
        to_str = _format_aggregate_date(to_date)
        url = urljoin(self.base_url + '/', f"v2/aggs/ticker/{ticker}/range/1/day/{from_str}/{to_str}")
        r = self._get(url, {'adjusted':'true', 'sort':'asc', 'limit':50000, 'apiKey':self.api_key}, ticker, f"from {from_str} to {to_str}")
        rows = r.json().get('results', [])
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df['trading_date'] = pd.to_datetime(df['t'], unit='ms', utc=True).dt.tz_convert('America/New_York').dt.date.astype(str)
        df = df.rename(columns={'o':'open','h':'high','l':'low','c':'close','v':'volume','vw':'vwap'})
        if 'vwap' not in df.columns:
            df['vwap'] = None
        df['ticker'] = ticker
        df['source'] = 'massive'
        df['fetched_at'] = datetime.utcnow()
        return df[['ticker','trading_date','open','high','low','close','volume','vwap','source','fetched_at']]
