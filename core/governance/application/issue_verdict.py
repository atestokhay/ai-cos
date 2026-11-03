"""IssueVerdict use-case: evaluate an action and persist the resulting Verdict."""

from core.contracts.governance import ActionContext, Decision, GovernanceVerdict, PermissionLevel
from core.governance.application.ports import PolicyPort, VerdictStorePort
from core.governance.domain.policy import evaluate


class IssueVerdict:
    def __init__(self, policy_port: PolicyPort, verdict_store: VerdictStorePort) -> None:
        self._policy_port = policy_port
        self._verdict_store = verdict_store

    def execute(self, ctx: ActionContext) -> GovernanceVerdict:
        policy = self._policy_port.load_policy()
        verdict = evaluate(ctx, policy)
        self._verdict_store.write(verdict)
        return GovernanceVerdict(
            decision=verdict.decision,
            permission_level=verdict.permission_level,
            reason=verdict.reason,
            approval_required=(
                verdict.decision == Decision.ALLOW
                and verdict.permission_level == PermissionLevel.L3
            ),
        )
