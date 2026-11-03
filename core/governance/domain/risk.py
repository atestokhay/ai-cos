"""Code-generated risk summaries for ApprovalRequests.

The risk summary is generated deterministically from the structured action payload.
A model must never be used to generate a risk summary (business-rules §9.3).
"""

from core.contracts.governance import ActionContext, PermissionLevel


_LEVEL_DESCRIPTIONS: dict[PermissionLevel, str] = {
    PermissionLevel.L0: "read-only or sandbox-local",
    PermissionLevel.L1: "reversible internal change",
    PermissionLevel.L2: "internal change requiring independent review",
    PermissionLevel.L3: "requires founder approval",
    PermissionLevel.L4: "forbidden for agents",
}


class RiskSummarizer:
    def summarize(self, ctx: ActionContext, payload: dict) -> str:
        level_desc = _LEVEL_DESCRIPTIONS.get(ctx.permission_level, "unknown level")
        arg_count = len(ctx.arguments)
        arg_keys = ", ".join(sorted(ctx.arguments.keys())) if ctx.arguments else "(none)"
        payload_keys = ", ".join(sorted(payload.keys())) if payload else "(none)"
        return (
            f"Tool: {ctx.tool} | "
            f"Level: {ctx.permission_level} ({level_desc}) | "
            f"Actor: {ctx.actor_id} | "
            f"Argument keys ({arg_count}): {arg_keys} | "
            f"Payload keys: {payload_keys}"
        )
