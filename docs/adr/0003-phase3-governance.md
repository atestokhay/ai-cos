# ADR-0003 — Phase 3: Governance Engine

- **Status:** Implemented (Phase 3 complete).
- **Decided by:** Founder
- **Date:** 2026-11-04
- **Scope:** Phase 3 only. Items explicitly marked deferred are addressed in a later ADR.

## Context

Phase 2 established the model routing and gateway pipeline, but the gateway forwarded all requests without policy enforcement. The architecture document (`§2`, `§3.3`, `§4.1`) requires that a code-enforced governance layer, independent of agents and the Orchestrator, controls all model and tool calls. Business rules (`§9`) define deny-by-default evaluation, an L0–L4 permission model, passkey-verified expiring approvals bound to payload hashes, an append-only hash-chained audit log, and an emergency stop mechanism.

Phase 3 implements this control layer within the existing modular monolith, without introducing new infrastructure or premature microservices.

## Decisions

### 1. Governance is code, not an agent

Governance decisions are made by a pure deterministic function (`evaluate()` in `core/governance/domain/policy.py`). No language model is consulted for a policy decision at any point. This is a hard requirement from the architecture document and business rules (`§9.1`).

### 2. Enforcement point: Gateway, not Orchestrator

The enforcement point is `apps/gateway/execution/pipeline.py` (`ExecutionPipeline`). The Orchestrator does not exist in Phase 3 and must not be the enforcement point: it is an agent-layer component, while governance is a control layer outside the hierarchy (`architecture §2`). The `GovernancePort` protocol is designed to be reused by the future Worker and Runner without reimplementing the enforcement logic.

`GovernanceDeniedError` inherits directly from `Exception`, not from any `ProviderError` subclass, and is not in the pipeline's retry-eligible set. It is raised before the retry loop in both `execute()` and `stream()`.

### 3. Deny-by-default policy evaluation

```python
# core/governance/domain/policy.py
def evaluate(ctx: ActionContext, policy: Policy) -> Verdict:
    required_level = policy.rules.get(ctx.tool)
    if required_level is None:
        return Verdict(..., permission_level=L4, decision=DENY,
                       reason="unknown tools are L4/deny")
    if required_level == L4:
        return Verdict(..., permission_level=L4, decision=DENY)
    return Verdict(..., decision=ALLOW)
```

The policy is a `dict[tool_name → PermissionLevel]`. An absent entry is L4/deny. An L4 entry is always deny regardless of actor.

### 4. L0–L4 semantics

Taken verbatim from `business-rules §9.2`. Not invented or extended in Phase 3.

| Level | Meaning |
|---|---|
| L0 | Read-only / sandbox-local |
| L1 | Reversible internal |
| L2 | Internal change requiring independent review |
| L3 | Founder approval required |
| L4 | Forbidden for agents |

### 5. Governance database role (D4 isolation)

A dedicated `governance` PostgreSQL role is provisioned by:
- `docker/postgres/init/01-create-roles.sh` — runs once on empty volume (uses `CREATE ROLE IF NOT EXISTS`).
- `docker/postgres/ensure-roles.sh` — runs as `postgres` superuser on every `compose up` before migrations, using conditional SQL (`\gset` + `\if`). This fixes existing volumes that predate the role.

The `app` role receives **no** privileges on any governance table. This is enforced by migration GRANTs and verified by integration tests that assert `sqlstate == 42501` for every table × operation.

Minimum grants per table:

| Table | governance grants | Rationale |
|---|---|---|
| `policy_version` | `INSERT, SELECT` | Governance records active policy versions |
| `verdict` | `INSERT, SELECT` | Append-only write path; SELECT for audit |
| `approval` | `INSERT, SELECT, UPDATE` | UPDATE needed for `consume`/`reject`/`expire` transitions |
| `budget` | `SELECT` | Read-only; caps set by founder outside the app role |
| `emergency_state` | `SELECT` | Read by Gateway admission checks |
| `audit_log` | `INSERT, SELECT` | No UPDATE or DELETE — append-only by privilege |

### 6. Schema decisions

- **Primary keys:** UUIDv7 for all governance tables, generated via `core/foundation/ids.new_uuid7()`. Natural identifiers (e.g. `git_commit`) remain plain strings.
- **Verdict–Approval cardinality:** 1:0..1. `approval.verdict_id` is a FK with a `UNIQUE` constraint. No separate join table.
- **`verdict.step_id`:** Nullable `UUID`. No FK constraint in Phase 3; the `step` table does not exist. The FK will be added in the phase that introduces Step/Workflow tables.
- **`approval.status` SQL values:** `pending | approved | rejected | expired | consumed`. Enforced by a `CHECK` constraint on the column.
- **FK on-delete:** `RESTRICT` for `approval.verdict_id → verdict.id`.

### 7. Approval integrity

All constraints enforced in `core/governance/application/`:

- **Payload-hash binding.** `payload_hash = SHA-256(canonical_json(payload))`. Stored on `ApprovalRequest`. `ConsumeApproval` recomputes and rejects on mismatch. A changed payload requires a new `ApprovalRequest`.
- **Single-use.** `SqlApprovalStore.consume()` runs `UPDATE … WHERE status = 'approved' AND consumed_time IS NULL`. Raises `ValueError` if `rowcount == 0` (concurrent consumption or already consumed).
- **Expiring.** `ConsumeApproval` checks `now >= request.expiry` before calling the store.
- **Code-generated risk summaries.** `RiskSummarizer` produces the summary from the structured payload using a deterministic template renderer. No model is involved.
- **No batch L3.** `RequestApproval.execute()` raises `ValueError` if `payload` is a `list`.
- **No pre-approved automations in V1.** Every L3 action requires a fresh `ApprovalRequest`. No stored blanket-approval path exists.
- **Self-approval of L4 actions is blocked.** L4 → always deny; no approval path exists for L4 actions.
- **Silence is not approval.** A missing or non-`approved` status returns `DENY`.

### 8. AuditLog: append-only, hash-chained (concurrency hardening deferred)

```
row N: { id, event, actor, subject, previous_row_hash = SHA-256(row N-1 canonical) }
row 0: { ..., previous_row_hash = SHA-256("") }   # sentinel
```

`SqlAuditLog.append()` performs the read of the previous row's hash and the insert inside the same `engine.begin()` transaction. The `governance` role receives only `INSERT, SELECT`; it has no `UPDATE` or `DELETE` grant.

**Known limitation:** the transaction does not serialize concurrent appenders. Two transactions can read the same chain head and insert sibling rows, forking the chain. The Phase 3 implementation does not yet use a transaction-scoped advisory lock or a locked chain-head row. This must be fixed and covered by a concurrent-writer integration test before production use. A hash chain alone also cannot stop a sufficiently privileged database actor from rewriting the full chain; independent verification and external anchoring are required for stronger tamper evidence.

### 8.1 Governance dependency wiring

`ExecutionPipeline` currently accepts an optional `GovernancePort`. If constructed with `governance=None`, the admission check is skipped. The gateway composition root must always inject the concrete governance adapter. A mandatory dependency and a production-composition test remain outstanding.

### 9. EmergencyState

`emergency_state` is read-only for the `governance` role. Any uncleared row blocks the pipeline. Three levels: `agent_quarantine`, `department_pause`, `company_wide_stop`.

### 10. Import-linter contracts added (3 new)

```toml
# pyproject.toml — contracts #10, #11, #12
[[tool.importlinter.contracts]]
name = "governance module layering"
type = "layers"
containers = ["core.governance"]
layers = ["infrastructure", "application", "domain"]

[[tool.importlinter.contracts]]
name = "governance domain and application stay framework free"
type = "forbidden"
source_modules = ["core.governance.domain", "core.governance.application"]
forbidden_modules = ["fastapi", "starlette", "sqlalchemy", "psycopg", "httpx"]

[[tool.importlinter.contracts]]
name = "gateway routes must not reach governance infrastructure"
type = "forbidden"
source_modules = ["apps.gateway.routes"]
forbidden_modules = ["core.governance.infrastructure"]
```

The exhaustive layers contract (#2) was updated to include `governance`:
```
layers = ["health | model_router | governance", "contracts | foundation"]
```

## Production security requirements (not built in Phase 3)

The following controls are required before governance data is used in production decisions:

1. **WebAuthn passkey verification** — `passkey_assertion_reference` is stored; the actual challenge/response flow is not implemented. The challenge must be bound to `request_id + payload_hash`. Full WebAuthn integration is deferred.
2. **Git-backed policy storage** — `SqlPolicyStore.load_policy()` returns a deny-all stub in Phase 3. Real policy rules must be loaded from a Git-versioned policy file before governance can allow any action other than the hardcoded model_call path.
3. **Daily AuditLog chain verification** — the schema supports it (`previous_row_hash` on every row); the scheduled verification and object-storage export are not implemented.

## Deferred

- **WebAuthn passkey verification.** See above. Schema (`passkey_assertion_reference`) is in place.
- **Git-backed policy storage.** `SqlPolicyStore.load_policy()` is a stub returning deny-all. Deferred to the phase that introduces policy file management.
- **`AuthorizedAsset`.** Limits security testing scope; deferred to the Cybersecurity phase.
- **`verdict.step_id` FK constraint.** Column exists (nullable UUID); FK deferred until `step` table exists (Phase 4+).
- **Daily AuditLog chain verification and object-storage export.** Schema supports it.
- **Worker/Runner `GovernancePort` integration.** The `GovernancePort` Protocol and `ActionContext`/`GovernanceVerdict` DTOs in `core/contracts/governance.py` are designed to be reused when Worker and Runner are implemented.
- **`reporting` DB role.** Still deferred per ADR-0001.
- **Budget enforcement at model-call time.** `SqlBudgetStore` reads budget records; the reservation and hard-stop logic (cost reserved before every model call, 50%/80%/100% thresholds) is not yet wired into the pipeline.
