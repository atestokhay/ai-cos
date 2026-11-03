"""TrackUsage use-case: persist a normalized UsageRecord via the UsageStorePort."""

from core.model_router.application.ports import UsageStorePort
from core.model_router.domain.usage import UsageRecord


class TrackUsage:
    def __init__(self, store: UsageStorePort) -> None:
        self._store = store

    def __call__(self, record: UsageRecord) -> None:
        self._store.record(record)
