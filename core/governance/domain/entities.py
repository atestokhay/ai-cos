"""Governance domain entities. Frozen dataclasses; no framework dependencies."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from core.governance.domain.enums import (
    ApprovalStatus,
    BudgetScope,
    Decision,
    EmergencyLevel,
    PermissionLevel,
)


@dataclass(frozen=True)
class PolicyVersion:
    id: uuid.UUID
    git_commit: str
    activation_time: datetime


@dataclass(frozen=True)
class Verdict:
    id: uuid.UUID
    action_hash: str
    tool: str
    redacted_arguments: str
    permission_level: PermissionLevel
    decision: Decision
    reason: str
    policy_version_id: uuid.UUID
    step_id: uuid.UUID | None = None


@dataclass(frozen=True)
class ApprovalRequest:
    id: uuid.UUID
    verdict_id: uuid.UUID
    payload_hash: str
    risk_summary: str
    status: ApprovalStatus
    expiry: datetime
    consumed_time: datetime | None = None
    passkey_assertion_reference: str | None = None


@dataclass(frozen=True)
class Budget:
    id: uuid.UUID
    scope: BudgetScope
    scope_id: str
    cap: Decimal
    set_by: str


@dataclass(frozen=True)
class EmergencyState:
    id: uuid.UUID
    level: EmergencyLevel
    scope: str
    who: str
    reason: str
    cleared_by: str | None = None


@dataclass(frozen=True)
class AuditEntry:
    id: uuid.UUID
    event: str
    actor: str
    subject: str
    previous_row_hash: str
