"""Abstract ports (Protocol interfaces) for the governance application layer."""

import uuid
from datetime import datetime
from typing import Protocol

from core.contracts.governance import (
    ActionContext,
    BudgetScope,
    GovernanceVerdict,
    EmergencyStateDTO,
)
from core.governance.domain.entities import (
    ApprovalRequest,
    Budget,
    EmergencyState,
    PolicyVersion,
    Verdict,
)
from core.governance.domain.policy import Policy


class ApprovalStorePort(Protocol):
    def create_request(self, request: ApprovalRequest) -> None: ...
    def get_by_id(self, request_id: uuid.UUID) -> ApprovalRequest | None: ...
    def consume(self, request_id: uuid.UUID, consumed_time: datetime) -> None: ...
    def reject(self, request_id: uuid.UUID) -> None: ...
    def expire_before(self, cutoff: datetime) -> int: ...


class VerdictStorePort(Protocol):
    def write(self, verdict: Verdict) -> None: ...


class PolicyPort(Protocol):
    def active_version(self) -> PolicyVersion: ...
    def load_policy(self) -> Policy: ...


class EmergencyStatePort(Protocol):
    def current(self) -> EmergencyState | None: ...


class BudgetPort(Protocol):
    def get(self, scope: BudgetScope, scope_id: str) -> Budget | None: ...


class GovernancePort(Protocol):
    def admit(self, ctx: ActionContext) -> GovernanceVerdict: ...
    def emergency_state(self) -> EmergencyStateDTO | None: ...
