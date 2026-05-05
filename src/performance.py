from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import logging
import os
from time import perf_counter
from typing import Iterator


LOGGER = logging.getLogger(__name__)


def perf_debug_enabled() -> bool:
    return os.getenv('WBM_PERF_DEBUG', '').strip().casefold() in {'1', 'true', 'yes', 'on'}


@dataclass
class PerfTimer:
    page: str
    enabled: bool = field(default_factory=perf_debug_enabled)
    timings: list[tuple[str, float]] = field(default_factory=list)
    _start: float = field(default_factory=perf_counter)

    @contextmanager
    def measure(self, label: str) -> Iterator[None]:
        start = perf_counter()
        try:
            yield
        finally:
            self.add(label, perf_counter() - start)

    def add(self, label: str, seconds: float) -> None:
        if not self.enabled:
            return
        self.timings.append((label, seconds))
        LOGGER.info('%s: %s %.3fs', self.page, label, seconds)

    def finish(self) -> None:
        self.add('total page data/render path', perf_counter() - self._start)

    def rows(self) -> list[dict]:
        return [
            {'Step': label, 'Seconds': round(seconds, 3)}
            for label, seconds in self.timings
        ]


def render_perf_debug(st, timer: PerfTimer) -> None:
    if not timer.enabled:
        return
    timer.finish()
    with st.expander('Performance / Debug', expanded=False):
        st.caption('Set WBM_PERF_DEBUG=1 to show page timing instrumentation.')
        st.dataframe(timer.rows(), width='stretch', hide_index=True)
