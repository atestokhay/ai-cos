"""Governance policy evaluation. Deny-by-default; never delegates to a model."""

import hashlib
import json
import uuid
from dataclasses import dataclass, field

from core.contracts.governance import ActionContext
from core.governance.domain.entities import Verdict
from core.governance.domain.enums import Decision, PermissionLevel
from core.foundation.ids import new_uuid7


@dataclass(frozen=True)
class Policy:
    """Maps tool names to the minimum PermissionLevel required to execute them.
    Unknown tools are treated as L4 (forbidden for agents)."""

    rules: dict[str, PermissionLevel] = field(default_factory=dict)
    policy_version_id: uuid.UUID = field(default_factory=new_uuid7)


def _action_hash(ctx: ActionContext) -> str:
    canonical = json.dumps(
        {"tool": ctx.tool, "arguments": ctx.arguments, "actor_id": ctx.actor_id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def _redact(ctx: ActionContext) -> str:
    """Return a redacted argument string safe for audit storage."""
    keys = sorted(ctx.arguments.keys())
    return json.dumps({k: "***" for k in keys}, sort_keys=True)


def evaluate(ctx: ActionContext, policy: Policy) -> Verdict:
    """Pure function: map ActionContext + Policy -> Verdict.

    Unknown tool → DENY at L4 (business-rules §9.1: an unknown tool counts as L4).
    """
    required_level = policy.rules.get(ctx.tool)

    if required_level is None:
        return Verdict(
            id=new_uuid7(),
            action_hash=_action_hash(ctx),
            tool=ctx.tool,
            redacted_arguments=_redact(ctx),
            permission_level=PermissionLevel.L4,
            decision=Decision.DENY,
            reason=f"tool '{ctx.tool}' is not in policy; unknown tools are L4/deny",
            policy_version_id=policy.policy_version_id,
        )

    # L4 tools are forbidden for agents regardless of actor.
    if required_level == PermissionLevel.L4:
        return Verdict(
            id=new_uuid7(),
            action_hash=_action_hash(ctx),
            tool=ctx.tool,
            redacted_arguments=_redact(ctx),
            permission_level=PermissionLevel.L4,
            decision=Decision.DENY,
            reason=f"tool '{ctx.tool}' is L4-forbidden for agents",
            policy_version_id=policy.policy_version_id,
        )

    return Verdict(
        id=new_uuid7(),
        action_hash=_action_hash(ctx),
        tool=ctx.tool,
        redacted_arguments=_redact(ctx),
        permission_level=required_level,
        decision=Decision.ALLOW,
        reason=f"tool '{ctx.tool}' allowed at {required_level}",
        policy_version_id=policy.policy_version_id,
    )
