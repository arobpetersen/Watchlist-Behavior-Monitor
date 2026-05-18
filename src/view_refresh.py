from __future__ import annotations

from collections.abc import Callable

from src.data_health_indicator import load_data_health_summary
from src.database import get_connection
from src.materialized_monitor_history import materialize_monitor_history
from src.monitor_history_loader import MONITOR_HISTORY_CACHE_VERSION, load_cached_monitor_history


DERIVED_REFRESH_MESSAGE = 'Derived views refreshed from database.'


def _clear_cached_function(func: Callable) -> str | None:
    clear = getattr(func, 'clear', None)
    if clear is None:
        return None
    clear()
    return getattr(func, '__name__', repr(func))


def refresh_derived_watchlist_views(
    *page_cached_loaders: Callable,
    db_path: str | None = None,
    rebuild_materialized_history: bool = False,
) -> list[str]:
    """Clear cached app-derived views that read local DuckDB watchlist state.

    This intentionally avoids the global Streamlit cache clear; raw market-data caches and
    unrelated Streamlit caches should not be invalidated by metadata edits.
    """
    cleared = []
    if rebuild_materialized_history and db_path:
        con = get_connection(db_path)
        result = materialize_monitor_history(
            con,
            db_path=db_path,
            source='refresh_derived_watchlist_views',
            cache_version=MONITOR_HISTORY_CACHE_VERSION,
        )
        cleared.append(f'materialized_monitor_history:{result.row_count}')
    for func in (
        load_cached_monitor_history,
        load_data_health_summary,
        *page_cached_loaders,
    ):
        name = _clear_cached_function(func)
        if name is not None:
            cleared.append(name)
    return cleared
