"""ConsumeApproval use-case: single-use, payload-hash-verified approval consumption."""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from core.governance.application.ports import ApprovalStorePort
from core.governance.domain.enums import ApprovalStatus


class ApprovalConsumeError(Exception):
    """Raised when an approval cannot be consumed."""


def _payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


class ConsumeApproval:
    def __init__(self, store: ApprovalStorePort) -> None:
        self._store = store

    def execute(self, request_id: uuid.UUID, payload: dict[str, Any]) -> None:
        request = self._store.get_by_id(request_id)
        if request is None:
            raise ApprovalConsumeError(f"approval request {request_id} not found")

        # Silence is not approval (business-rules §9.3).
        if request.status != ApprovalStatus.APPROVED:
            raise ApprovalConsumeError(
                f"approval {request_id} has status '{request.status}'; "
                "only 'approved' approvals can be consumed"
            )

        now = datetime.now(timezone.utc)
        if now >= request.expiry:
            raise ApprovalConsumeError(
                f"approval {request_id} expired at {request.expiry}"
            )

        # A changed payload invalidates the approval (business-rules §9.3).
        if _payload_hash(payload) != request.payload_hash:
            raise ApprovalConsumeError(
                f"payload hash mismatch for approval {request_id}; "
                "the payload has changed and a new approval is required"
            )

        # Single-use check.
        if request.consumed_time is not None:
            raise ApprovalConsumeError(
                f"approval {request_id} has already been consumed"
            )

        self._store.consume(request_id, now)
