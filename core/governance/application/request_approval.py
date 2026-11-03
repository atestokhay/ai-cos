"""RequestApproval use-case: create a single-payload ApprovalRequest."""

import hashlib
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from core.contracts.governance import ActionContext, PermissionLevel
from core.governance.application.ports import ApprovalStorePort
from core.governance.domain.entities import ApprovalRequest
from core.governance.domain.enums import ApprovalStatus
from core.governance.domain.risk import RiskSummarizer
from core.foundation.ids import new_uuid7

# Default expiry window for L3 approval requests.
_DEFAULT_EXPIRY_MINUTES = 30

_risk_summarizer = RiskSummarizer()


def _payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


class RequestApproval:
    def __init__(self, store: ApprovalStorePort) -> None:
        self._store = store

    def execute(
        self,
        ctx: ActionContext,
        payload: dict[str, Any],
        verdict_id: uuid.UUID,
        expiry_minutes: int = _DEFAULT_EXPIRY_MINUTES,
    ) -> ApprovalRequest:
        # No batch L3 approval (business-rules §9.3).
        if isinstance(payload, list):
            raise ValueError(
                "Batch approval is not permitted; submit one payload at a time"
            )

        # Only L3 actions require approval (L4 is always DENY, L0-L2 are auto-allowed).
        if ctx.permission_level != PermissionLevel.L3:
            raise ValueError(
                f"Approval requests are only valid for L3 actions; "
                f"got {ctx.permission_level}"
            )

        now = datetime.now(timezone.utc)
        request = ApprovalRequest(
            id=new_uuid7(),
            verdict_id=verdict_id,
            payload_hash=_payload_hash(payload),
            risk_summary=_risk_summarizer.summarize(ctx, payload),
            status=ApprovalStatus.PENDING,
            expiry=now + timedelta(minutes=expiry_minutes),
        )
        self._store.create_request(request)
        return request
