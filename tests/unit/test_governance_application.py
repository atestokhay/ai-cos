"""Unit tests for governance application layer use-cases."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from core.contracts.governance import ActionContext, Decision, PermissionLevel
from core.governance.application.consume_approval import (
    ApprovalConsumeError,
    ConsumeApproval,
)
from core.governance.application.expire_approvals import ExpireApprovals
from core.governance.application.issue_verdict import IssueVerdict
from core.governance.application.reject_approval import ApprovalRejectError, RejectApproval
from core.governance.application.request_approval import RequestApproval
from core.governance.domain.entities import ApprovalRequest, Verdict
from core.governance.domain.enums import ApprovalStatus, Decision as DomainDecision
from core.governance.domain.policy import Policy


def _ctx(tool: str, level: PermissionLevel = PermissionLevel.L0) -> ActionContext:
    return ActionContext(
        tool=tool,
        arguments={"key": "value"},
        actor_id="actor-1",
        permission_level=level,
    )


def _future(minutes: int = 30) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def _past(minutes: int = 1) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)


def _approval(
    *,
    status: ApprovalStatus = ApprovalStatus.APPROVED,
    expiry: datetime | None = None,
    consumed_time: datetime | None = None,
    payload_hash: str = "abc123",
) -> ApprovalRequest:
    return ApprovalRequest(
        id=uuid.uuid4(),
        verdict_id=uuid.uuid4(),
        payload_hash=payload_hash,
        risk_summary="summary",
        status=status,
        expiry=expiry or _future(),
        consumed_time=consumed_time,
    )


class TestIssueVerdict:
    def test_allowed_tool_returns_allow_verdict(self):
        policy_port = MagicMock()
        policy_port.load_policy.return_value = Policy(
            rules={"read_repo": PermissionLevel.L0},
            policy_version_id=uuid.uuid4(),
        )
        verdict_store = MagicMock()

        uc = IssueVerdict(policy_port, verdict_store)
        result = uc.execute(_ctx("read_repo", PermissionLevel.L0))

        assert result.decision == Decision.ALLOW
        verdict_store.write.assert_called_once()

    def test_unknown_tool_returns_deny(self):
        policy_port = MagicMock()
        policy_port.load_policy.return_value = Policy(rules={}, policy_version_id=uuid.uuid4())
        verdict_store = MagicMock()

        result = IssueVerdict(policy_port, verdict_store).execute(_ctx("unknown"))
        assert result.decision == Decision.DENY

    def test_l3_tool_requires_approval(self):
        policy_port = MagicMock()
        policy_port.load_policy.return_value = Policy(
            rules={"deploy": PermissionLevel.L3},
            policy_version_id=uuid.uuid4(),
        )
        result = IssueVerdict(policy_port, MagicMock()).execute(
            _ctx("deploy", PermissionLevel.L0)
        )
        assert result.approval_required is True

    def test_l0_tool_does_not_require_approval(self):
        policy_port = MagicMock()
        policy_port.load_policy.return_value = Policy(
            rules={"read": PermissionLevel.L0},
            policy_version_id=uuid.uuid4(),
        )
        result = IssueVerdict(policy_port, MagicMock()).execute(_ctx("read", PermissionLevel.L0))
        assert result.approval_required is False


class TestRequestApproval:
    def test_creates_approval_request(self):
        store = MagicMock()
        uc = RequestApproval(store)
        ctx = _ctx("deploy", PermissionLevel.L3)
        req = uc.execute(ctx, {"target": "prod"}, uuid.uuid4())

        assert req.status == ApprovalStatus.PENDING
        assert req.payload_hash != ""
        store.create_request.assert_called_once_with(req)

    def test_no_batch_approval_raises(self):
        store = MagicMock()
        uc = RequestApproval(store)
        with pytest.raises(ValueError, match="[Bb]atch"):
            uc.execute(_ctx("deploy", PermissionLevel.L3), [], uuid.uuid4())

    def test_non_l3_raises(self):
        store = MagicMock()
        uc = RequestApproval(store)
        with pytest.raises(ValueError, match="L3"):
            uc.execute(_ctx("read", PermissionLevel.L0), {"k": "v"}, uuid.uuid4())

    def test_risk_summary_is_code_generated(self):
        store = MagicMock()
        req = RequestApproval(store).execute(
            _ctx("deploy", PermissionLevel.L3), {"env": "prod"}, uuid.uuid4()
        )
        assert len(req.risk_summary) > 0
        assert "deploy" in req.risk_summary


class TestConsumeApproval:
    def _hash(self, payload: dict) -> str:
        import hashlib, json
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def test_consumes_valid_approval(self):
        payload = {"env": "prod"}
        store = MagicMock()
        store.get_by_id.return_value = _approval(payload_hash=self._hash(payload))

        ConsumeApproval(store).execute(uuid.uuid4(), payload)
        store.consume.assert_called_once()

    def test_pending_status_raises(self):
        store = MagicMock()
        store.get_by_id.return_value = _approval(status=ApprovalStatus.PENDING)
        with pytest.raises(ApprovalConsumeError, match="pending"):
            ConsumeApproval(store).execute(uuid.uuid4(), {})

    def test_expired_raises(self):
        payload = {}
        store = MagicMock()
        store.get_by_id.return_value = _approval(
            expiry=_past(), payload_hash=self._hash(payload)
        )
        with pytest.raises(ApprovalConsumeError, match="expir"):
            ConsumeApproval(store).execute(uuid.uuid4(), payload)

    def test_payload_hash_mismatch_raises(self):
        store = MagicMock()
        store.get_by_id.return_value = _approval(payload_hash="wrong_hash")
        with pytest.raises(ApprovalConsumeError, match="[Hh]ash|mismatch"):
            ConsumeApproval(store).execute(uuid.uuid4(), {"env": "prod"})

    def test_already_consumed_raises(self):
        payload = {}
        store = MagicMock()
        store.get_by_id.return_value = _approval(
            consumed_time=_past(), payload_hash=self._hash(payload)
        )
        with pytest.raises(ApprovalConsumeError, match="[Cc]onsum"):
            ConsumeApproval(store).execute(uuid.uuid4(), payload)

    def test_missing_approval_raises(self):
        store = MagicMock()
        store.get_by_id.return_value = None
        with pytest.raises(ApprovalConsumeError, match="not found"):
            ConsumeApproval(store).execute(uuid.uuid4(), {})


class TestRejectApproval:
    def test_rejects_pending(self):
        store = MagicMock()
        store.get_by_id.return_value = _approval(status=ApprovalStatus.PENDING)
        RejectApproval(store).execute(uuid.uuid4())
        store.reject.assert_called_once()

    def test_cannot_reject_consumed(self):
        store = MagicMock()
        store.get_by_id.return_value = _approval(status=ApprovalStatus.CONSUMED)
        with pytest.raises(ApprovalRejectError):
            RejectApproval(store).execute(uuid.uuid4())

    def test_missing_raises(self):
        store = MagicMock()
        store.get_by_id.return_value = None
        with pytest.raises(ApprovalRejectError, match="not found"):
            RejectApproval(store).execute(uuid.uuid4())


class TestExpireApprovals:
    def test_delegates_to_store(self):
        store = MagicMock()
        store.expire_before.return_value = 3
        result = ExpireApprovals(store).execute()
        assert result == 3
        store.expire_before.assert_called_once()
