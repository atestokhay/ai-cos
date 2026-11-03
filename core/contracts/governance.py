"""Cross-boundary DTOs and shared enumerations for governance contracts."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class PermissionLevel(StrEnum):
    L0 = "l0"
    L1 = "l1"
    L2 = "l2"
    L3 = "l3"
    L4 = "l4"


class Decision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class BudgetScope(StrEnum):
    RUN = "run"
    TASK = "task"
    PROJECT = "project"
    DEPARTMENT = "department"
    DAY = "day"
    MONTH = "month"


class EmergencyLevel(StrEnum):
    AGENT_QUARANTINE = "agent_quarantine"
    DEPARTMENT_PAUSE = "department_pause"
    COMPANY_WIDE_STOP = "company_wide_stop"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONSUMED = "consumed"


class ActionContext(BaseModel):
    model_config = {"frozen": True}

    tool: str
    arguments: dict[str, Any]
    actor_id: str
    permission_level: PermissionLevel


class GovernanceVerdict(BaseModel):
    model_config = {"frozen": True}

    decision: Decision
    permission_level: PermissionLevel
    reason: str
    approval_required: bool


class EmergencyStateDTO(BaseModel):
    model_config = {"frozen": True}

    level: EmergencyLevel
    scope: str
