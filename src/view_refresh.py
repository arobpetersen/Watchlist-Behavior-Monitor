from __future__ import annotations

from collections.abc import Callable

from src.data_health_indicator import load_data_health_summary
from src.monitor_history_loader import load_cached_monitor_history


DERIVED_REFRESH_MESSAGE = 'Derived views refreshed from database.'


def _clear_cached_function(func: Callable) -> str | None:
    clear = getattr(func, 'clear', None)
    if clear is None:
        return None
    clear()
    return getattr(func, '__name__', repr(func))


def refresh_derived_watchlist_views(*page_cached_loaders: Callable) -> list[str]:
    """Clear cached app-derived views that read local DuckDB watchlist state.

    This intentionally avoids the global Streamlit cache clear; raw market-data caches and
    unrelated Streamlit caches should not be invalidated by metadata edits.
    """
    cleared = []
    for func in (
        load_cached_monitor_history,
        load_data_health_summary,
        *page_cached_loaders,
    ):
        name = _clear_cached_function(func)
        if name is not None:
            cleared.append(name)
    return cleared
