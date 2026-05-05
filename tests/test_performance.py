from __future__ import annotations

from src.performance import PerfTimer, perf_debug_enabled


def test_perf_debug_enabled_uses_env_flag(monkeypatch):
    monkeypatch.delenv('WBM_PERF_DEBUG', raising=False)
    assert perf_debug_enabled() is False

    monkeypatch.setenv('WBM_PERF_DEBUG', '1')
    assert perf_debug_enabled() is True


def test_perf_timer_records_only_when_enabled():
    disabled = PerfTimer('Test', enabled=False)
    disabled.add('step', 0.1)
    assert disabled.rows() == []

    enabled = PerfTimer('Test', enabled=True)
    enabled.add('step', 0.1234)
    assert enabled.rows() == [{'Step': 'step', 'Seconds': 0.123}]
