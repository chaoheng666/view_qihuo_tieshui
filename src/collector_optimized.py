from __future__ import annotations

from .collector import FuturesDataCollector


class OptimizedFuturesCollector(FuturesDataCollector):
    pass


_collector_instance = OptimizedFuturesCollector()


def get_collector_instance() -> OptimizedFuturesCollector:
    return _collector_instance
