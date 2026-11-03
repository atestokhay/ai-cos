from typing import Protocol

from core.health.domain.status import HealthStatus


class DatabaseProbe(Protocol):
    def is_reachable(self) -> bool: ...


class CheckReadiness:
    def __init__(self, probe: DatabaseProbe) -> None:
        self._probe = probe

    def __call__(self) -> HealthStatus:
        return HealthStatus.OK if self._probe.is_reachable() else HealthStatus.UNAVAILABLE
