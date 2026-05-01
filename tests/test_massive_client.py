from __future__ import annotations

import requests

from src.massive_client import MassiveClient


class DummyResponse:
    status_code = 400
    reason = 'Bad Request'

    def raise_for_status(self):
        raise requests.HTTPError('400 Client Error')


def test_fetch_intraday_formats_datetime_date(monkeypatch):
    calls = []

    class EmptyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {'results': []}

    def fake_get(url, params, timeout):
        calls.append((url, params, timeout))
        return EmptyResponse()

    monkeypatch.setattr('src.massive_client.requests.get', fake_get)

    client = MassiveClient('secret-key', 'https://api.polygon.io')
    client.fetch_intraday_1m('AAPL', '2026-04-30 00:00:00')

    url, _, _ = calls[0]
    assert url.endswith('/v2/aggs/ticker/AAPL/range/1/minute/2026-04-30/2026-04-30')
    assert ' ' not in url


def test_fetch_intraday_error_message_hides_api_key(monkeypatch):
    def fake_get(url, params, timeout):
        return DummyResponse()

    monkeypatch.setattr('src.massive_client.requests.get', fake_get)

    client = MassiveClient('secret-key', 'https://api.polygon.io')
    try:
        client.fetch_intraday_1m('AAPL', '2026-04-30')
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError('Expected RuntimeError')

    assert 'AAPL' in message
    assert '2026-04-30' in message
    assert '400 Bad Request' in message
    assert 'secret-key' not in message
    assert 'apiKey' not in message
    assert 'https://api.polygon.io' not in message


def test_fetch_daily_formats_date_range(monkeypatch):
    calls = []

    class EmptyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {'results': []}

    def fake_get(url, params, timeout):
        calls.append((url, params, timeout))
        return EmptyResponse()

    monkeypatch.setattr('src.massive_client.requests.get', fake_get)

    client = MassiveClient('secret-key', 'https://api.polygon.io')
    client.fetch_daily('AAPL', '2026-03-16 00:00:00', '2026-05-04 00:00:00')

    url, _, _ = calls[0]
    assert url.endswith('/v2/aggs/ticker/AAPL/range/1/day/2026-03-16/2026-05-04')
    assert ' ' not in url


def test_fetch_daily_connection_error_hides_api_key(monkeypatch):
    def fake_get(url, params, timeout):
        raise requests.ConnectionError(f'failed for {url}?apiKey={params["apiKey"]}')

    monkeypatch.setattr('src.massive_client.requests.get', fake_get)

    client = MassiveClient('secret-key', 'https://api.polygon.io')
    try:
        client.fetch_daily('AAPL', '2026-03-16', '2026-05-04')
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError('Expected RuntimeError')

    assert 'AAPL' in message
    assert 'ConnectionError' in message
    assert 'secret-key' not in message
    assert 'apiKey' not in message
    assert 'https://api.polygon.io' not in message
