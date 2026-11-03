"""Integration tests for governance against the real PostgreSQL container.

Run inside the api container:
    sudo docker compose exec -T api pytest -q -p no:cacheprovider tests/integration/test_governance.py

The api container runs as the 'app' role (DB_USER=app). These fixtures construct
their own connections using the role-specific password env vars so that all tests
can run in a single pytest invocation without changing DB_USER.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import URL, create_engine, text
from sqlalchemy.exc import DBAPIError

from core.foundation.ids import new_uuid7
from core.governance.domain.entities import AuditEntry
from core.governance.domain.enums import ApprovalStatus, Decision, PermissionLevel
from core.governance.infrastructure.sql_governance import (
    SqlAuditLog,
    SqlApprovalStore,
    SqlVerdictStore,
    _SENTINEL_HASH,
    _audit_chain_hash,
)

INSUFFICIENT_PRIVILEGE = "42501"

GOVERNANCE_TABLES = [
    "policy_version",
    "verdict",
    "approval",
    "budget",
    "emergency_state",
    "audit_log",
]


def _make_engine(username: str, password: str):
    url = URL.create(
        "postgresql+psycopg",
        username=username,
        password=password,
        host=os.environ.get("DB_HOST", "db"),
        port=int(os.environ.get("DB_PORT", "5432")),
        database=os.environ.get("DB_NAME", "aicos"),
    )
    return create_engine(url, pool_size=2, pool_timeout=10, pool_pre_ping=True)


@pytest.fixture(scope="module")
def governance_engine():
    """Engine connected as the 'governance' role."""
    e = _make_engine("governance", os.environ["GOVERNANCE_DB_PASSWORD"])
    yield e
    e.dispose()


@pytest.fixture(scope="module")
def app_engine():
    """Engine connected as 'app' role for privilege-denial assertions."""
    e = _make_engine("app", os.environ["APP_DB_PASSWORD"])
    yield e
    e.dispose()


def _seed_policy_version(engine) -> uuid.UUID:
    pv_id = new_uuid7()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO policy_version (id, git_commit, activation_time) "
                "VALUES (:id, :gc, :at)"
            ),
            {
                "id": str(pv_id),
                "gc": "abc123",
                "at": datetime.now(timezone.utc),
            },
        )
    return pv_id


class TestRoleProvisioning:
    """governance role must exist with the correct attributes and table privileges."""

    def test_governance_role_exists(self, governance_engine) -> None:
        with governance_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT rolcanlogin, rolsuper, rolcreaterole, rolcreatedb "
                    "FROM pg_roles WHERE rolname = 'governance'"
                )
            ).one_or_none()
        assert row is not None, "governance role does not exist"
        assert row.rolcanlogin is True
        assert row.rolsuper is False
        assert row.rolcreaterole is False
        assert row.rolcreatedb is False

    def test_governance_has_connect_on_database(self, governance_engine) -> None:
        with governance_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT has_database_privilege('governance', current_database(), 'CONNECT') "
                    "AS can_connect"
                )
            ).one()
        assert row.can_connect is True

    def test_governance_has_usage_on_public_schema(self, governance_engine) -> None:
        with governance_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT has_schema_privilege('governance', 'public', 'USAGE') AS can_use"
                )
            ).one()
        assert row.can_use is True

    # Per-table minimum privilege assertions.
    # Expected grants per table (governance role):
    #   policy_version  : INSERT, SELECT
    #   verdict         : INSERT, SELECT
    #   approval        : INSERT, SELECT, UPDATE
    #   budget          : SELECT only
    #   emergency_state : SELECT only
    #   audit_log       : INSERT, SELECT  (no UPDATE/DELETE — append-only)

    @pytest.mark.parametrize(
        "table,privilege,expected",
        [
            # policy_version
            ("policy_version", "INSERT", True),
            ("policy_version", "SELECT", True),
            ("policy_version", "UPDATE", False),
            ("policy_version", "DELETE", False),
            # verdict
            ("verdict", "INSERT", True),
            ("verdict", "SELECT", True),
            ("verdict", "UPDATE", False),
            ("verdict", "DELETE", False),
            # approval (needs UPDATE for status transitions)
            ("approval", "INSERT", True),
            ("approval", "SELECT", True),
            ("approval", "UPDATE", True),
            ("approval", "DELETE", False),
            # budget — read-only
            ("budget", "INSERT", False),
            ("budget", "SELECT", True),
            ("budget", "UPDATE", False),
            ("budget", "DELETE", False),
            # emergency_state — read-only
            ("emergency_state", "INSERT", False),
            ("emergency_state", "SELECT", True),
            ("emergency_state", "UPDATE", False),
            ("emergency_state", "DELETE", False),
            # audit_log — append-only
            ("audit_log", "INSERT", True),
            ("audit_log", "SELECT", True),
            ("audit_log", "UPDATE", False),
            ("audit_log", "DELETE", False),
        ],
    )
    def test_governance_table_privilege(
        self, governance_engine, table: str, privilege: str, expected: bool
    ) -> None:
        with governance_engine.connect() as conn:
            result = conn.execute(
                text(
                    f"SELECT has_table_privilege('governance', '{table}', '{privilege}') AS ok"
                )
            ).scalar_one()
        assert result is expected, (
            f"governance.{table} {privilege}: expected {expected}, got {result}"
        )


class TestAppRoleIsolation:
    """The app role must have no access to any governance table (D4 isolation)."""

    @pytest.mark.parametrize("table", GOVERNANCE_TABLES)
    def test_app_role_cannot_select_governance_table(self, app_engine, table: str) -> None:
        with pytest.raises(DBAPIError) as exc_info:
            with app_engine.connect() as conn:
                conn.execute(text(f"SELECT 1 FROM {table} LIMIT 1")).fetchall()
        assert exc_info.value.orig.sqlstate == INSUFFICIENT_PRIVILEGE

    def test_app_role_cannot_insert_into_verdict(self, app_engine) -> None:
        with pytest.raises(DBAPIError) as exc_info:
            with app_engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO verdict (id, action_hash, tool, redacted_arguments, "
                        "permission_level, decision, reason, policy_version_id) "
                        "VALUES (:id, 'h', 't', '{}', 'l0', 'allow', 'r', :pv)"
                    ),
                    {"id": str(new_uuid7()), "pv": str(uuid.uuid4())},
                )
        assert exc_info.value.orig.sqlstate == INSUFFICIENT_PRIVILEGE


class TestVerdictStore:
    def test_write_and_retrieve(self, governance_engine) -> None:
        pv_id = _seed_policy_version(governance_engine)
        store = SqlVerdictStore(governance_engine)
        from core.governance.domain.entities import Verdict

        verdict = Verdict(
            id=new_uuid7(),
            action_hash="hash1",
            tool="read_repo",
            redacted_arguments='{"path":"***"}',
            permission_level=PermissionLevel.L0,
            decision=Decision.ALLOW,
            reason="allowed",
            policy_version_id=pv_id,
        )
        store.write(verdict)

        with governance_engine.connect() as conn:
            row = conn.execute(
                text("SELECT tool, decision FROM verdict WHERE id = :id"),
                {"id": str(verdict.id)},
            ).one()
        assert row.tool == "read_repo"
        assert row.decision == "allow"


class TestApprovalStore:
    def test_create_and_consume(self, governance_engine) -> None:
        pv_id = _seed_policy_version(governance_engine)
        verdict_id = new_uuid7()
        with governance_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO verdict (id, action_hash, tool, redacted_arguments, "
                    "permission_level, decision, reason, policy_version_id) "
                    "VALUES (:id, 'h2', 'deploy', '{}', 'l3', 'allow', 'ok', :pv)"
                ),
                {"id": str(verdict_id), "pv": str(pv_id)},
            )

        from core.governance.domain.entities import ApprovalRequest

        store = SqlApprovalStore(governance_engine)
        req = ApprovalRequest(
            id=new_uuid7(),
            verdict_id=verdict_id,
            payload_hash="ph1",
            risk_summary="risk",
            status=ApprovalStatus.APPROVED,
            expiry=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        store.create_request(req)

        fetched = store.get_by_id(req.id)
        assert fetched is not None
        assert fetched.status == ApprovalStatus.APPROVED

        now = datetime.now(timezone.utc)
        store.consume(req.id, now)

        fetched2 = store.get_by_id(req.id)
        assert fetched2.status == ApprovalStatus.CONSUMED
        assert fetched2.consumed_time is not None

    def test_idempotent_consume_does_not_change_first_consumed_time(
        self, governance_engine
    ) -> None:
        pv_id = _seed_policy_version(governance_engine)
        verdict_id = new_uuid7()
        with governance_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO verdict (id, action_hash, tool, redacted_arguments, "
                    "permission_level, decision, reason, policy_version_id) "
                    "VALUES (:id, 'h3', 'deploy', '{}', 'l3', 'allow', 'ok', :pv)"
                ),
                {"id": str(verdict_id), "pv": str(pv_id)},
            )

        from core.governance.domain.entities import ApprovalRequest

        store = SqlApprovalStore(governance_engine)
        req = ApprovalRequest(
            id=new_uuid7(),
            verdict_id=verdict_id,
            payload_hash="ph2",
            risk_summary="risk",
            status=ApprovalStatus.APPROVED,
            expiry=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        store.create_request(req)

        t1 = datetime.now(timezone.utc)
        store.consume(req.id, t1)
        # Second consume: WHERE clause won't match (consumed_time IS NOT NULL), no-op.
        store.consume(req.id, datetime.now(timezone.utc) + timedelta(seconds=5))

        fetched = store.get_by_id(req.id)
        assert fetched.consumed_time.replace(microsecond=0) == t1.replace(microsecond=0)


class TestAuditLogChain:
    def test_hash_chain_is_consistent(self, governance_engine) -> None:
        audit = SqlAuditLog(governance_engine)

        e1 = audit.append("test.event.1", "actor-1", "subject-1")
        e2 = audit.append("test.event.2", "actor-1", "subject-2")
        e3 = audit.append("test.event.3", "actor-1", "subject-3")

        # e2.previous_row_hash must equal the hash of e1's fields
        assert e2.previous_row_hash == _audit_chain_hash(e1)
        # e3.previous_row_hash must equal the hash of e2's fields
        assert e3.previous_row_hash == _audit_chain_hash(e2)

    def test_app_role_cannot_insert_audit_log(self, app_engine) -> None:
        with pytest.raises(DBAPIError) as exc_info:
            with app_engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO audit_log (id, event, actor, subject, previous_row_hash) "
                        "VALUES (:id, 'e', 'a', 's', :h)"
                    ),
                    {"id": str(new_uuid7()), "h": _SENTINEL_HASH},
                )
        assert exc_info.value.orig.sqlstate == INSUFFICIENT_PRIVILEGE
