"""Unit tests for governance domain: policy evaluation and risk summarizer."""

import uuid

from core.contracts.governance import ActionContext, Decision, PermissionLevel
from core.governance.domain.policy import Policy, evaluate
from core.governance.domain.risk import RiskSummarizer


def _ctx(tool: str, level: PermissionLevel = PermissionLevel.L0) -> ActionContext:
    return ActionContext(
        tool=tool,
        arguments={"arg1": "val1"},
        actor_id="test-actor",
        permission_level=level,
    )


class TestDenyByDefault:
    def test_unknown_tool_is_denied_at_l4(self):
        policy = Policy(rules={}, policy_version_id=uuid.uuid4())
        verdict = evaluate(_ctx("unknown_tool"), policy)
        assert verdict.decision == Decision.DENY
        assert verdict.permission_level == PermissionLevel.L4
        assert "unknown_tool" in verdict.reason

    def test_empty_policy_denies_all_tools(self):
        policy = Policy(rules={}, policy_version_id=uuid.uuid4())
        for tool in ("read_file", "write_file", "execute", "deploy"):
            assert evaluate(_ctx(tool), policy).decision == Decision.DENY


class TestPermissionLevelAssignment:
    def test_l0_tool_allowed(self):
        policy = Policy(
            rules={"read_repo": PermissionLevel.L0},
            policy_version_id=uuid.uuid4(),
        )
        verdict = evaluate(_ctx("read_repo"), policy)
        assert verdict.decision == Decision.ALLOW
        assert verdict.permission_level == PermissionLevel.L0

    def test_l1_tool_allowed(self):
        policy = Policy(
            rules={"create_branch": PermissionLevel.L1},
            policy_version_id=uuid.uuid4(),
        )
        verdict = evaluate(_ctx("create_branch"), policy)
        assert verdict.decision == Decision.ALLOW
        assert verdict.permission_level == PermissionLevel.L1

    def test_l2_tool_allowed(self):
        policy = Policy(
            rules={"merge_pr": PermissionLevel.L2},
            policy_version_id=uuid.uuid4(),
        )
        verdict = evaluate(_ctx("merge_pr"), policy)
        assert verdict.decision == Decision.ALLOW
        assert verdict.permission_level == PermissionLevel.L2

    def test_l3_tool_allowed(self):
        policy = Policy(
            rules={"deploy_production": PermissionLevel.L3},
            policy_version_id=uuid.uuid4(),
        )
        verdict = evaluate(_ctx("deploy_production"), policy)
        assert verdict.decision == Decision.ALLOW
        assert verdict.permission_level == PermissionLevel.L3

    def test_l4_tool_always_denied(self):
        policy = Policy(
            rules={"change_policy": PermissionLevel.L4},
            policy_version_id=uuid.uuid4(),
        )
        verdict = evaluate(_ctx("change_policy"), policy)
        assert verdict.decision == Decision.DENY
        assert verdict.permission_level == PermissionLevel.L4

    def test_verdict_references_policy_version(self):
        policy_id = uuid.uuid4()
        policy = Policy(
            rules={"read_repo": PermissionLevel.L0},
            policy_version_id=policy_id,
        )
        verdict = evaluate(_ctx("read_repo"), policy)
        assert verdict.policy_version_id == policy_id

    def test_verdict_has_unique_id(self):
        policy = Policy(rules={"t": PermissionLevel.L0}, policy_version_id=uuid.uuid4())
        v1 = evaluate(_ctx("t"), policy)
        v2 = evaluate(_ctx("t"), policy)
        assert v1.id != v2.id

    def test_verdict_redacts_arguments(self):
        policy = Policy(rules={"read_repo": PermissionLevel.L0}, policy_version_id=uuid.uuid4())
        ctx = ActionContext(
            tool="read_repo",
            arguments={"path": "/secret/file", "token": "abc123"},
            actor_id="actor",
            permission_level=PermissionLevel.L0,
        )
        verdict = evaluate(ctx, policy)
        assert "secret" not in verdict.redacted_arguments
        assert "abc123" not in verdict.redacted_arguments
        assert "path" in verdict.redacted_arguments
        assert "token" in verdict.redacted_arguments


class TestRiskSummarizer:
    def test_summary_contains_tool_and_level(self):
        summarizer = RiskSummarizer()
        ctx = ActionContext(
            tool="deploy_production",
            arguments={"env": "prod"},
            actor_id="actor",
            permission_level=PermissionLevel.L3,
        )
        summary = summarizer.summarize(ctx, {"target": "prod"})
        assert "deploy_production" in summary
        assert "l3" in summary.lower()

    def test_summary_is_deterministic(self):
        summarizer = RiskSummarizer()
        ctx = ActionContext(
            tool="merge_pr",
            arguments={"pr": "42"},
            actor_id="actor",
            permission_level=PermissionLevel.L2,
        )
        s1 = summarizer.summarize(ctx, {"payload": "data"})
        s2 = summarizer.summarize(ctx, {"payload": "data"})
        assert s1 == s2
