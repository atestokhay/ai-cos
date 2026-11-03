"""SQL-backed governance infrastructure adapters.

All adapters use raw SQLAlchemy Engine connections (no ORM), following the
pattern established in core.model_router.infrastructure.
"""

import hashlib
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Engine, text

from core.contracts.governance import BudgetScope, EmergencyLevel
from core.foundation.ids import new_uuid7
from core.governance.domain.entities import (
    ApprovalRequest,
    AuditEntry,
    Budget,
    EmergencyState,
    PolicyVersion,
    Verdict,
)
from core.governance.domain.enums import (
    ApprovalStatus,
    Decision,
    PermissionLevel,
)
from core.governance.domain.policy import Policy


# SHA-256 of the empty string — sentinel for the first audit_log row.
_SENTINEL_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _audit_chain_hash(entry: AuditEntry) -> str:
    """Compute SHA-256 of this row's canonical fields for the NEXT row's previous_row_hash."""
    canonical = (
        str(entry.id)
        + entry.event
        + entry.actor
        + entry.subject
        + entry.previous_row_hash
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


class SqlVerdictStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write(self, verdict: Verdict) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO verdict (
                        id, step_id, action_hash, tool, redacted_arguments,
                        permission_level, decision, reason, policy_version_id, issued_at
                    ) VALUES (
                        :id, :step_id, :action_hash, :tool, :redacted_arguments,
                        :permission_level, :decision, :reason, :policy_version_id, :issued_at
                    )
                    """
                ),
                {
                    "id": str(verdict.id),
                    "step_id": str(verdict.step_id) if verdict.step_id else None,
                    "action_hash": verdict.action_hash,
                    "tool": verdict.tool,
                    "redacted_arguments": verdict.redacted_arguments,
                    "permission_level": verdict.permission_level.value,
                    "decision": verdict.decision.value,
                    "reason": verdict.reason,
                    "policy_version_id": str(verdict.policy_version_id),
                    "issued_at": datetime.now(timezone.utc),
                },
            )


class SqlApprovalStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_request(self, request: ApprovalRequest) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO approval (
                        id, verdict_id, payload_hash, risk_summary, status,
                        expiry, consumed_time, passkey_assertion_reference, created_at
                    ) VALUES (
                        :id, :verdict_id, :payload_hash, :risk_summary, :status,
                        :expiry, :consumed_time, :passkey_assertion_reference, :created_at
                    )
                    """
                ),
                {
                    "id": str(request.id),
                    "verdict_id": str(request.verdict_id),
                    "payload_hash": request.payload_hash,
                    "risk_summary": request.risk_summary,
                    "status": request.status.value,
                    "expiry": request.expiry,
                    "consumed_time": request.consumed_time,
                    "passkey_assertion_reference": request.passkey_assertion_reference,
                    "created_at": datetime.now(timezone.utc),
                },
            )

    def get_by_id(self, request_id: uuid.UUID) -> ApprovalRequest | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT id, verdict_id, payload_hash, risk_summary, status,
                           expiry, consumed_time, passkey_assertion_reference
                    FROM approval WHERE id = :id
                    """
                ),
                {"id": str(request_id)},
            ).one_or_none()
        if row is None:
            return None
        return ApprovalRequest(
            id=uuid.UUID(str(row.id)),
            verdict_id=uuid.UUID(str(row.verdict_id)),
            payload_hash=row.payload_hash,
            risk_summary=row.risk_summary,
            status=ApprovalStatus(row.status),
            expiry=row.expiry.replace(tzinfo=timezone.utc)
            if row.expiry.tzinfo is None
            else row.expiry,
            consumed_time=row.consumed_time,
            passkey_assertion_reference=row.passkey_assertion_reference,
        )

    def consume(self, request_id: uuid.UUID, consumed_time: datetime) -> None:
        with self._engine.begin() as conn:
            result = conn.execute(
                text(
                    "UPDATE approval SET status = 'consumed', consumed_time = :ct "
                    "WHERE id = :id AND status = 'approved' AND consumed_time IS NULL"
                ),
                {"id": str(request_id), "ct": consumed_time},
            )
        # rowcount == 0 means a concurrent caller already consumed or the approval
        # was not in the expected state — treat as a failed single-use check.
        if result.rowcount == 0:
            raise ValueError(
                f"approval {request_id} could not be consumed: "
                "already consumed, not approved, or does not exist"
            )

    def reject(self, request_id: uuid.UUID) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE approval SET status = 'rejected' "
                    "WHERE id = :id AND status IN ('pending', 'approved')"
                ),
                {"id": str(request_id)},
            )

    def expire_before(self, cutoff: datetime) -> int:
        with self._engine.begin() as conn:
            result = conn.execute(
                text(
                    "UPDATE approval SET status = 'expired' "
                    "WHERE expiry < :cutoff AND status IN ('pending', 'approved')"
                ),
                {"cutoff": cutoff},
            )
            return result.rowcount


class SqlPolicyStore:
    """Read-only policy store. Governance role has SELECT on policy_version."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def active_version(self) -> PolicyVersion:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT id, git_commit, activation_time "
                    "FROM policy_version ORDER BY activation_time DESC LIMIT 1"
                )
            ).one()
        return PolicyVersion(
            id=uuid.UUID(str(row.id)),
            git_commit=row.git_commit,
            activation_time=row.activation_time.replace(tzinfo=timezone.utc)
            if row.activation_time.tzinfo is None
            else row.activation_time,
        )

    def load_policy(self) -> Policy:
        """Phase 3 stub: returns a deny-all policy until policy storage is implemented.
        Policy rules will be loaded from Git in a future phase."""
        version = self.active_version()
        return Policy(rules={}, policy_version_id=version.id)


class SqlEmergencyStateStore:
    """Read-only emergency state store. Governance role has SELECT on emergency_state."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def current(self) -> EmergencyState | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT id, level, scope, who, reason, cleared_by "
                    "FROM emergency_state WHERE cleared_by IS NULL "
                    "ORDER BY created_at DESC LIMIT 1"
                )
            ).one_or_none()
        if row is None:
            return None
        return EmergencyState(
            id=uuid.UUID(str(row.id)),
            level=EmergencyLevel(row.level),
            scope=row.scope,
            who=row.who,
            reason=row.reason,
            cleared_by=row.cleared_by,
        )


class SqlBudgetStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get(self, scope: BudgetScope, scope_id: str) -> Budget | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT id, scope, scope_id, cap, set_by FROM budget "
                    "WHERE scope = :scope AND scope_id = :scope_id"
                ),
                {"scope": scope.value, "scope_id": scope_id},
            ).one_or_none()
        if row is None:
            return None
        return Budget(
            id=uuid.UUID(str(row.id)),
            scope=BudgetScope(row.scope),
            scope_id=row.scope_id,
            cap=Decimal(str(row.cap)),
            set_by=row.set_by,
        )


class SqlAuditLog:
    """Append-only, hash-chained audit log writer."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def _last_hash(self, conn) -> str:
        row = conn.execute(
            text(
                "SELECT previous_row_hash, event, actor, subject, id "
                "FROM audit_log ORDER BY recorded_at DESC LIMIT 1"
            )
        ).one_or_none()
        if row is None:
            return _SENTINEL_HASH
        last = AuditEntry(
            id=uuid.UUID(str(row.id)),
            event=row.event,
            actor=row.actor,
            subject=row.subject,
            previous_row_hash=row.previous_row_hash,
        )
        return _audit_chain_hash(last)

    def append(self, event: str, actor: str, subject: str) -> AuditEntry:
        entry_id = new_uuid7()
        with self._engine.begin() as conn:
            prev_hash = self._last_hash(conn)
            entry = AuditEntry(
                id=entry_id,
                event=event,
                actor=actor,
                subject=subject,
                previous_row_hash=prev_hash,
            )
            conn.execute(
                text(
                    """
                    INSERT INTO audit_log (id, event, actor, subject, previous_row_hash, recorded_at)
                    VALUES (:id, :event, :actor, :subject, :previous_row_hash, :recorded_at)
                    """
                ),
                {
                    "id": str(entry.id),
                    "event": entry.event,
                    "actor": entry.actor,
                    "subject": entry.subject,
                    "previous_row_hash": entry.previous_row_hash,
                    "recorded_at": datetime.now(timezone.utc),
                },
            )
        return entry
