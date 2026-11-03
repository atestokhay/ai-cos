import logging

import pytest
from sqlalchemy import create_engine

from core.health.application.check_readiness import CheckReadiness
from core.health.domain.status import HealthStatus
from core.health.infrastructure.sql_probe import SqlDatabaseProbe


class _StubProbe:
    def __init__(self, reachable: bool) -> None:
        self._reachable = reachable

    def is_reachable(self) -> bool:
        return self._reachable


@pytest.mark.parametrize(
    ("reachable", "expected"),
    [(True, HealthStatus.OK), (False, HealthStatus.UNAVAILABLE)],
)
def test_check_readiness_maps_probe_result(reachable: bool, expected: HealthStatus) -> None:
    assert CheckReadiness(_StubProbe(reachable))() is expected


def test_probe_failure_is_reported_without_connection_details(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Port 1 refuses immediately, so this exercises a real driver failure.
    engine = create_engine(
        "postgresql+psycopg://probe-user:probe-secret@127.0.0.1:1/probe-db",
        connect_args={"connect_timeout": 2},
    )

    with caplog.at_level(logging.WARNING):
        reachable = SqlDatabaseProbe(engine).is_reachable()

    engine.dispose()
    assert reachable is False
    assert "Database probe failed" in caplog.text
    for detail in ("probe-secret", "probe-user", "probe-db", "127.0.0.1"):
        assert detail not in caplog.text
