"""RejectApproval use-case."""

import uuid

from core.governance.application.ports import ApprovalStorePort
from core.governance.domain.enums import ApprovalStatus


class ApprovalRejectError(Exception):
    """Raised when an approval cannot be rejected."""


class RejectApproval:
    def __init__(self, store: ApprovalStorePort) -> None:
        self._store = store

    def execute(self, request_id: uuid.UUID) -> None:
        request = self._store.get_by_id(request_id)
        if request is None:
            raise ApprovalRejectError(f"approval request {request_id} not found")
        if request.status not in (ApprovalStatus.PENDING, ApprovalStatus.APPROVED):
            raise ApprovalRejectError(
                f"approval {request_id} cannot be rejected from status '{request.status}'"
            )
        self._store.reject(request_id)
