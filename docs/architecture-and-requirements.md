# AI-COS V1 — Architecture and Requirements

> This document defines the target architecture and technical requirements of AI-COS V1, including components that are not implemented yet. See the README for the current implementation status. Items described as assumptions or unapproved decisions must not be treated as final.

## Implementation status

| Phase | Scope | Status |
|---|---|---|
| Phase 1 | Modular monolith skeleton, PostgreSQL roles, health endpoints, Alembic, acceptance test | **Complete** |
| Phase 2 | Model Router, Gateway, DeepSeek adapter, circuit breaker, Cost Ledger | **Complete** |
| Phase 3 | Governance Engine — policy evaluation, approval lifecycle, EmergencyState, AuditLog, Budget | **Complete** (deferred items noted in §13) |
| Phase 4+ | Worker, job queue, Step/Run tables, Workflow Engine | Planned |
| Phase 5+ | Agent Engine, Orchestrator | Planned |
| Phase 6+ | Web UI (PWA), WebAuthn, Git-backed policy storage | Planned |

### Currently deployed components

```
apps/api      — health endpoints only
apps/gateway  — model execution + governance admission
```

All other deployable components listed in §3.2 (`apps/worker`, `apps/runner`, `apps/web`) are planned, not implemented.

### Current ASCII architecture

```
                        ┌──────────────────────────────────────────────┐
                        │  apps/  (transport and composition)           │
                        │                                               │
                        │  ┌─────────────┐    ┌──────────────────────┐ │
  HTTP (127.0.0.1) ────▶│  │  apps/api   │    │    apps/gateway      │ │
                        │  │  /health/*  │    │  /internal/model/*   │ │
                        │  │             │    │  ExecutionPipeline   │ │
                        │  │             │    │  GovernancePort      │ │
                        │  └──────┬──────┘    └──────────┬───────────┘ │
                        └─────────│──────────────────────│─────────────┘
                                  │                      │
                        ┌─────────▼──────────────────────▼─────────────┐
                        │  core/                                        │
                        │                                               │
                        │  ┌──────────┐  ┌────────────┐  ┌──────────┐  │
                        │  │  health  │  │model_router│  │governance│  │
                        │  │ domain   │  │  domain    │  │  domain  │  │
                        │  │ appl.    │  │  appl.     │  │  appl.   │  │
                        │  │ infra.   │  │  infra.    │  │  infra.  │  │
                        │  └────┬─────┘  └─────┬──────┘  └────┬─────┘  │
                        │       └───────────────┴──────────────┘        │
                        │                       │                       │
                        │  ┌────────────────────▼──────────────────┐   │
                        │  │  core/foundation (settings, DB engine) │   │
                        │  │  core/contracts  (shared Pydantic DTOs)│   │
                        │  └───────────────────────────────────────┘   │
                        └───────────────────────┬───────────────────────┘
                                                │
                        ┌───────────────────────▼───────────────────────┐
                        │  PostgreSQL 18                                  │
                        │                                               │
                        │  migrator role (DDL):  all tables             │
                        │  app role (DML):       model_registry (SEL)   │
                        │                        cost_ledger (INS+SEL)  │
                        │  governance role (DML):                       │
                        │    policy_version  (INS+SEL)                  │
                        │    verdict         (INS+SEL)                  │
                        │    approval        (INS+SEL+UPD)              │
                        │    budget          (SEL)                      │
                        │    emergency_state (SEL)                      │
                        │    audit_log       (INS+SEL, no UPD/DEL)      │
                        └───────────────────────────────────────────────┘

  apps/gateway ──────────────────────────▶ DeepSeek API (holds credential)

  ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄
  Planned: Orchestrator, Worker, Runner,
  Workflow/Agent/Memory/Initiative/Eval
  Engines, apps/web PWA
  ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄
```

## 1. Product scope

### 1.1 Long-term product direction
- AI-COS is the operating system of an AI-assisted product company in which the founder directs product design and strategic decisions.
- Product lines (`business_line`) are a configurable classification; their values are not hardcoded.
- The Cybersecurity department primarily protects the company's own code, infrastructure, accounts and products.

### 1.2 First operational release
- Initial active departments:
  1. Engineering
  2. Cybersecurity
  3. Creative & Design
  4. Business
  5. Marketing
- R&D is part of the long-term organization; it does not have to be fully active in the first operational release.
- In its first stage, AI-COS must support product development and software delivery flows.
- No V1 feature should be expanded unless real usage requires it.

## 2. Organization and working hierarchy

```text
Owner
  |
  v
Orchestrator
  |
  +-- Engineering Manager
  +-- Cybersecurity Manager
  +-- Creative & Design Manager
  +-- Business Manager
  +-- Marketing Manager
  +-- R&D Manager (later activation)
          |
          v
    Specialist Agents
```

- The founder holds final authority over strategy, product design, spending, publishing and policy.
- The Orchestrator is the founder's single operational point of contact.
- The Orchestrator is responsible for project registration, requirements analysis, briefs, plans, department assignment, dependency tracking and escalation.
- The Orchestrator does not assign routine tasks to specialists; it assigns work to department managers. Its own analysis tasks are the exception.
- Each Manager can assign work only to specialists in its own department.
- A Manager cannot directly assign work to staff in another department; it requests coordination through the Orchestrator.
- A Specialist does only the work within its assigned scope and sends structured records to its own manager.
- Governance is not an agent or a language model; it is a control layer enforced by code, outside the hierarchy.

## 3. Architectural approach

### 3.1 Modular monolith
- The initial architecture is a modular monolith with clear package boundaries in a single Python codebase.
- PostgreSQL serves as the durable system of record and the job queue.
- Kubernetes, Redis and a separate vector database are not planned for V1.
- A service is split out only for a different trust boundary or a measured scaling need.
- Package boundaries are enforced with import rules and separate database roles.

### 3.2 Deployable components
Five deployable components are defined:
- `apps/api`: authentication, command intake, queries, live updates and approval endpoints.
- `apps/worker`: takes jobs from the PostgreSQL queue, executes agent runs, sends heartbeats and reports results.
- `apps/gateway`: the privileged gateway for governance, the model router and tool adapters. Only this process holds external service credentials.
- `apps/runner`: runner daemon on a separate host, with isolated sandbox execution.
- `apps/web`: static PWA control panel.

Logical core packages:
- `core/orchestrator`
- `core/initiative_engine`
- `core/projects`
- `core/workflow_engine`
- `core/agent_engine`
- `core/model_router`
- `core/governance`
- `core/event_system`
- `core/memory_engine`
- `core/evaluation_engine`
- `core/contracts`
- `tools/`

### 3.3 Component responsibility boundaries
| Component | Responsibility | Must not |
|---|---|---|
| API | Authentication, command/query interface, approval API, live updates | Execute model or tool calls directly; make business policy decisions |
| Worker | Job claim, agent loop, heartbeat, result recording | Make policy decisions, hold credentials, keep durable state only in memory |
| Orchestrator | Project and plan coordination, requirements analysis, department assignment | Change or approve specifications, enforce policy, micromanage specialists |
| Initiative Engine | Scheduled or event-triggered work discovery; producing Proposals | Create work without approval or call models continuously |
| Project Engine | Specification versions, requirement ledger, brief, task graph, traceability | Invent requirements |
| Workflow Engine | Data-defined execution of stages, gates and dependencies | Hardcode workflow logic for a single product type |
| Agent Engine | Loading agent definitions, building context, model/tool loop, structured output validation | Run tools outside the gateway |
| Model Router | Provider adapter, tier, redaction, validation, usage/cost, retry | Make governance decisions or run outside the gateway |
| Governance | Permission, Approval, Budget/Resource, Audit/Compliance, Safety | Act on a model's final decision |
| Tool Registry | Typed tool definitions, argument validation, dispatch through the gateway | Execute operations without a governance verdict |
| Memory Engine | Sourced knowledge storage, retrieval and controlled promotion | Automatically turn model output into durable knowledge |
| Event System | Outbox, queue, lease, timer, notification | Carry business logic |
| Evaluation Engine | Golden tasks and agent/department metrics | Change agent definitions on its own |
| Runner | Creating, limiting, running and destroying sandboxes | Hold secrets or access the database |
| PWA | Management and approval interface | Contain business logic or secrets |

## 4. Trust boundaries and infrastructure

### 4.1 Control Plane
- The core server hosts the API, worker, PostgreSQL and gateway.
- The gateway is the privileged process and the only process holding provider, GitHub and runner credentials.
- Worker and API processes must not have these credentials.
- Database roles must be separated: `app`, `governance`, `reporting`.
- The governance database role must be used only by the gateway.

### 4.2 Execution Plane / Runner
- The Runner runs on a separate host; this separation is mandatory before generated code is executed.
- A single host may be used for an initial no-code-execution pilot; a separate runner host is required once generated code or code with third-party dependencies is executed.
- The Runner has no route or credentials to PostgreSQL.
- The Runner accepts only signed requests from the Control Plane.
- The Docker socket on the runner host is not mounted into sandboxes.
- Sandboxes are rootless and run as non-root inside the container.
- The base image is read-only; CPU, memory, disk, process and wall-clock limits apply.
- Sandboxes have no network egress by default. Where needed, an egress proxy with a short allowlist is defined.
- A sandbox is destroyed when its work ends; durable files stay in the project workspace volume.
- Code and dependencies leave the sandbox as patches or artifacts; Git push happens through the gateway.
- The Runner is assumed to be compromised, so it must hold no secrets.

### 4.3 Secret placement
| Secret | Location | Access |
|---|---|---|
| PostgreSQL credentials | Core server process environments | The relevant DB role; governance role for the gateway only |
| Model provider API key | Gateway environment | Gateway |
| GitHub App private key | Gateway | Gateway; issues short-lived installation tokens |
| Runner request-signing key | Gateway | The Runner holds only the verification public key |
| Passkey | Public key in the DB | Private key only on the founder's device |
| Backup encryption key | Backup job and the founder's offline copy | Backup process |
| The founder's personal accounts, cards and personal email | Not stored in AI-COS | Agent access forbidden |

## 5. Model layer

- V1 initially uses a single provider adapter; the provider is selected by configuration and is not built into the architecture.
- The provider abstraction must allow a second provider to be added; running multiple providers is not required in V1.
- Model names and tier mappings must be kept in configuration, not scattered through code.
- Tiers: `Fast`, `Reason`, `Deep`.
- A tier is a class of task capability, not a model name.
- Tier escalation happens only on objective triggers: at most two steps, without exceeding the agent ceiling or budget limit.
- Model selection is based on task type, quality need, latency, cost, context and capability flags.
- Provider capability flags: tool calls, JSON output, thinking, context size, vision.
- The worst-case cost is reserved before every model call.
- Model calls, tool calls and token usage are recorded.
- Provider errors and rate limit behavior are handled by the router.
- A model's reasoning text may be kept for redacted audit; it is not passed into another agent's context.
- Model output is data to be validated, not a control command.

### 5.1 Data classes
- `public`
- `project-confidential`: specifications, source code and plans.
- `restricted`: secrets, credentials, personal data and third-party data; never sent to a provider.
- Every block in a context carries a data class.
- The router rejects requests containing restricted data.
- The selected provider's data location and API retention/training terms must be assessed before any data is sent to that provider; accepting them requires a founder decision.

## 6. Task execution and durability

- An agent is active only during a run; agent definitions and records are durable, but agent processes are not kept running 24/7.
- A worker takes jobs from the PostgreSQL queue with a lease.
- Claiming uses row locking and `SKIP LOCKED`.
- When a lease expires, the job is requeued.
- A worker renews its lease with a heartbeat and reports step and cost progress.
- Timeouts apply to model and tool calls and at run and task level.
- Retries happen only on transient errors: at most 3 attempts, with exponential backoff and jitter.
- Policy denials and validation failures are not retried automatically.
- Jobs and tool calls carry an idempotency key.
- External adapters record intent and result around each attempt, before any retry.
- The target is at-least-once execution with idempotent effects; exactly-once is not guaranteed.
- The cancel flag is checked at every step and heartbeat.
- Emergency stop halts new leases, cancels current leases and terminates sandboxes.
- After an expired lease, the run continues from the last committed step if it is complete; otherwise it restarts from the beginning.
- A job that reaches its attempt limit becomes dead and an escalation is sent to the manager.
- An idle worker makes no model calls; it waits for a DB notification and uses a slow fallback check.

### 6.1 Initial values
These are starting assumptions, to be tuned:
- Lease: 60 seconds.
- Heartbeat: 15 seconds.
- Maximum attempts: 3.
- Maximum steps per run: 30.
- Run wall-clock: 20 minutes.
- Revision rounds: 2.
- Subtask depth: 3.
- Global model concurrency: 8.
- Autonomy lease check-in: 7 days.
- Context budget: Fast 4K, Reason 12K, Deep 30K tokens.
- These values must be re-evaluated against measurements from real usage.

## 7. Workspace and project requirements

- Each project is bound to its own Workspace.
- Each task explicitly carries its `project_id`/Workspace context.
- The active Workspace is the default context.
- A project explicitly named in the user's message takes precedence over the active Workspace.
- If the project is ambiguous, the Orchestrator asks for clarification before making changes.
- A Workspace ID alone does not grant authority; access is verified separately.
- Project-specific memory, source, artifacts, credentials and deployment config must not leak into another project.
- A single-company, single-owner model is used; no multi-tenant field is defined.
- Each project uses its own Workspace, repository, database project, environment and deployment configuration.

## 8. Control panel

- A mobile phone is the primary management interface.
- The interface must be an installable, mobile-first PWA.
- The phone and browser talk only to the API and hold no secrets.
- The development machine is only a client; production operations must not depend on it.
- Navigation: Today, Inbox, Projects, Company, Command.
- Emergency Stop is visible on every screen.
- V1 screens: Today, Inbox, Approval detail, Projects (Overview/Spec/Evidence/Cost), Command, Budget & Usage, Emergency Stop, Passkeys, Push.
- Later screens: Company scorecards, task trace, reports library, audit explorer and wider desktop polish.
- Authentication uses WebAuthn passkeys.
- At least two passkeys and offline recovery codes are required.
- Push notification categories: approval, blocked escalation, budget threshold, health alert, completion.
- Live screen updates use Server-Sent Events, with slow refresh as the fallback.
- The PWA shell is readable offline; actions require a connection. Approvals are not queued offline.
- Short-lived sessions, secure cookies, CSRF protection, CSP and endpoint rate limits are mandatory.
- No secrets or tokens are kept in browser storage.

## 9. Memory and knowledge management

- The whole repository or history is never loaded into context; a bounded, task-relevant context pack is built.
- Every memory record carries its source, date, scope and review status.
- A model statement alone cannot become durable knowledge.
- Memory types: company policies, department knowledge, project specifications, task history, agent working context, approved long-term lessons.
- Company policy is approved only by the founder, through Git.
- Department knowledge and lessons are merged after independent review.
- A project specification is the founder's original text, stored as immutable and versioned.
- Agent working context is untrusted and scoped to the same agent and project.
- Only approved memory enters retrieval for agents other than its author.
- Lesson promotion without a source is rejected.
- V1 search uses PostgreSQL full-text search; there is no separate vector DB.
- A vector extension may be considered only if golden task measurements show retrieval is inadequate.

## 10. Cost control and limits

- Token estimates are assumptions until the first 50 real runs have been measured.
- Cap values are configured by the founder; they are not code constants.
- Six budget scopes: run, task, project, department, day, month.
- At 50% usage, an event is recorded; at 80%, the manager is warned and the founder notified; at 100%, new model calls stop for that scope.
- The provider's prepaid balance is a second, independent upper limit.
- Hosting, domain, API, subscription, auto-renewal and usage-based charges need founder approval in advance. AI-COS cannot make a purchase without approval.

## 11. V1 acceptance criteria

- [ ] The Orchestrator receives user commands as typed records.
- [ ] The Orchestrator resolves the correct Workspace and asks when it is ambiguous.
- [ ] The Orchestrator assigns tasks to Managers; Managers assign tasks to their own specialists.
- [ ] Agent outputs pass schema validation.
- [ ] Task state is changed only by the runtime.
- [ ] Governance controls all model and tool calls.
- [ ] Worker and Runner hold no secrets.
- [ ] The Runner has no network access to PostgreSQL.
- [ ] L3/L4 rules are enforced by code.
- [ ] Approval is bound to the exact payload hash, passkey verified, expiring and single-use.
- [ ] Emergency stop has been tested.
- [ ] Budget reservation and hard stop work.
- [ ] GitHub CI produces independent test evidence.
- [ ] The PWA provides task, approval and status tracking from a phone.
- [ ] A backup restore attempt completes successfully.
- [ ] Tests, security findings, cost and incomplete requirements are reported.

## 12. Governance engine (Phase 3 implementation)

This section documents the Phase 3 implementation. See [ADR-0003](adr/0003-phase3-governance.md) for decisions and rationale.

### 12.1 Principles (implemented)

Governance is not an agent. It is a code-enforced control layer outside the agent hierarchy (`architecture §2`). The key implemented rules:
- **Deny-by-default.** An unknown tool or unknown argument pattern returns `Decision.DENY` at `PermissionLevel.L4`.
- **Models are not policy authorities.** The `evaluate()` function is a pure deterministic function; no model is consulted.
- **Single enforcement point.** `GovernancePort` is injected into `ExecutionPipeline` in `apps/gateway`. Every `execute()` and `stream()` call runs the admission check before any provider I/O.

### 12.2 Admission check sequence

```
execute() / stream()
    │
    ▼
1. EmergencyState check  ─── active state found ──▶ GovernanceDeniedError (not retried)
    │
    ▼
2. Policy admit (evaluate ActionContext)
    │
    ├── DENY ──────────────────────────────────────▶ GovernanceDeniedError (not retried)
    │
    └── ALLOW (approval_required=false) ──▶ provider call proceeds
         │
         └── ALLOW (approval_required=true, L3)
                 │
                 ▼
             Verify ApprovalRequest:
               status == approved
               not expired
               payload_hash matches current payload
               consumed_time is None
             ──── fails ──▶ GovernanceDeniedError
             ──── passes ─▶ consume() atomically ─▶ provider call proceeds
```

`GovernanceDeniedError` inherits directly from `Exception`, not from any `ProviderError` subclass, and is not in the retry-eligible set.

### 12.3 L0–L4 permission levels

| Level | Meaning | Examples |
|---|---|---|
| L0 | Read-only / sandbox-local | Reading an authorized repo, sandbox test/build |
| L1 | Reversible internal | Feature branch, commit, PR, internal record |
| L2 | Internal change requiring independent review | Default branch merge, staging deploy |
| L3 | Founder approval required | Production deploy, publish, spend, credential change |
| L4 | Forbidden for agents | Changing governance/policy/audit, approving own work, raw secrets |

Unknown tool → L4/deny. L4 → always deny regardless of actor.

### 12.4 Approval integrity constraints (implemented)

- **Payload-hash binding.** `ApprovalRequest.payload_hash` is `SHA-256(canonical_json(payload))`. `ConsumeApproval` recomputes the hash and rejects if it does not match the stored value.
- **Single-use.** `consume()` runs `UPDATE … WHERE status = 'approved' AND consumed_time IS NULL`; raises `ValueError` if `rowcount == 0` (already consumed or status changed).
- **Expiring.** `ConsumeApproval` checks `now >= request.expiry` before calling the store.
- **Code-generated risk summaries.** `RiskSummarizer` produces the summary from the structured payload. No model is involved.
- **No batch L3.** `RequestApproval.execute()` raises `ValueError` if `payload` is a list.
- **No pre-approved automations in V1.** Every L3 action requires a fresh `ApprovalRequest`.

**Deferred:** WebAuthn passkey verification. The `passkey_assertion_reference` column exists in the `approval` table and the passkey challenge is designed to be bound to `request_id + payload_hash`, but the actual WebAuthn challenge/response flow is not implemented. The current stub accepts a `None` reference.

### 12.5 AuditLog hash chain (implemented)

Every row stores `previous_row_hash = SHA-256(id || event || actor || subject || previous_row_hash)` of the preceding row. The first row stores the SHA-256 of the empty string as a known sentinel. The `SELECT` for the previous hash and the `INSERT` for the new row execute inside the same `engine.begin()` transaction. No `UPDATE` or `DELETE` is granted on `audit_log`.

Deferred: daily chain verification and export of the chain head to object storage.

### 12.6 EmergencyState (implemented)

The `emergency_state` table is read-only for the `governance` role. `SqlEmergencyStateStore.current()` returns the most recent uncleared row. Any active state blocks the pipeline.

Three levels: `agent_quarantine`, `department_pause`, `company_wide_stop`.

### 12.7 Database role separation (implemented)

The `governance` role is provisioned by `docker/postgres/ensure-roles.sh` (runs as `postgres` superuser on every `compose up`) and by `docker/postgres/init/01-create-roles.sh` (runs once on empty volume). Both scripts use `IF NOT EXISTS` or conditional logic.

The `app` role has zero privileges on all six governance tables. This is verified by integration tests that assert `sqlstate == 42501` for every table × operation.

**Deferred:** `reporting` DB role (architecture §4.1).

## 13. Deferred features

- Active use of a second model provider.
- A separate vector database or semantic search.
- Automatic lesson promotion.
- An advanced repository map.
- Advanced analytics and report screens.
- Fully automatic rollback.
- Image, audio and 3D asset generation tools.
- Platform-specific build infrastructure.
- Advanced microVM isolation.
- Multiple runners and runner pools by sensitivity level.
- Fully controlled autonomy, considered only after advanced-stage gates are passed.
