from __future__ import annotations

from src.view_refresh import DERIVED_REFRESH_MESSAGE, refresh_derived_watchlist_views


class FakeCachedLoader:
    __name__ = 'fake_cached_loader'

    def __init__(self):
        self.clear_count = 0

    def clear(self):
        self.clear_count += 1


def test_refresh_derived_watchlist_views_clears_passed_page_loaders():
    loader = FakeCachedLoader()

    cleared = refresh_derived_watchlist_views(loader)

    assert loader.clear_count == 1
    assert 'fake_cached_loader' in cleared
    assert DERIVED_REFRESH_MESSAGE == 'Derived views refreshed from database.'


def test_refresh_helper_avoids_broad_streamlit_cache_clear():
    source = open('src/view_refresh.py', encoding='utf-8').read()

    assert 'st.cache_data.clear' not in source
    assert 'cache_data.clear' not in source
