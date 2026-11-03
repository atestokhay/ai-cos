# AI-COS

[![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Docker Compose](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)](compose.yaml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests: 158/158 passing](https://img.shields.io/badge/tests-158%2F158%20passing-brightgreen)](#tests)

**AI-COS: A security-first modular monolith foundation for orchestrating autonomous AI agents and complex workflows.**

> **Status: Phases 1–3 complete.** The service skeleton, database security model, model routing, gateway, and governance engine are implemented. Agents, workflows, the web UI, and the Orchestrator are not yet implemented. The service is not production-ready. `docs/` specifies the full target system, including components that do not exist yet.

## Quickstart

You need Docker Engine with the Compose plugin. The daemon does not start automatically; start it with `sudo systemctl start docker.service`. If your user is not in the `docker` group, prefix all `docker` commands with `sudo`.

**1. Clone the repository**

```bash
git clone https://github.com/<atestokhay>/ai-cos.git
cd ai-cos
```

**2. Create `.env` with generated passwords**

```bash
cp .env.example .env && chmod 600 .env
for v in POSTGRES_PASSWORD MIGRATOR_DB_PASSWORD APP_DB_PASSWORD GOVERNANCE_DB_PASSWORD; do
  sed -i "s/^$v=.*/$v=$(openssl rand -hex 32)/" .env
done
```

**3. Start the stack**

```bash
sudo docker compose up -d --build --wait
curl http://127.0.0.1:8000/health/ready    # {"status":"ok"}
```

Stop it with `sudo docker compose down`. **`sudo docker compose down -v` permanently deletes the development database.**

## Why it is built this way

**PostgreSQL least privilege.** Three database roles are enforced: `migrator` (DDL only), `app` (DML on model routing tables), and `governance` (DML on governance tables). No role ever holds privileges it does not use. `app` cannot touch governance tables and vice versa. `CREATE TABLE`, `CREATE SCHEMA`, and `CREATE TEMP TABLE` are rejected with SQLSTATE `42501` for both runtime roles. Privileges inherited through `PUBLIC` are revoked, and runtime roles cannot connect to other databases.

**Layer boundaries enforced by tests.** `import-linter` runs in the test suite with 12 contracts, so a boundary violation fails the build instead of waiting for code review:

- `core` cannot import `apps`.
- `domain` and `application` layers within every `core` module cannot import FastAPI, SQLAlchemy, Psycopg, or httpx.
- Routes cannot reach `infrastructure`.
- Application code cannot import Alembic.
- A new `core` package fails the layering check until it is explicitly added to the layers contract.

**A modular monolith instead of premature microservices.** There is one codebase with explicit module boundaries. A service gets split out only for a different trust boundary or a measured scaling need.

**A small network surface.** PostgreSQL publishes no host port, the API is published only on `127.0.0.1`, and both the API and migration images run as a non-root user. The `runtime` image contains no development dependencies.

**Governance is code, not an LLM.** Policy decisions are made by a deterministic evaluator. No model is a policy authority. Deny-by-default: unknown tools and unknown argument patterns return L4/deny.

## Architecture

```
                        ┌──────────────────────────────────────────────┐
                        │  apps/  (transport and composition)           │
                        │                                               │
                        │  ┌─────────────┐    ┌──────────────────────┐ │
                        │  │  apps/api   │    │    apps/gateway      │ │
  HTTP (127.0.0.1) ────▶│  │  /health/*  │    │  /internal/model/*   │ │
                        │  │             │    │  ExecutionPipeline   │ │
                        │  └──────┬──────┘    └──────────┬───────────┘ │
                        └─────────│──────────────────────│─────────────┘
                                  │                      │
                        ┌─────────▼──────────────────────▼─────────────┐
                        │  core/  (no HTTP knowledge)                   │
                        │                                               │
                        │  ┌──────────┐  ┌────────────┐  ┌──────────┐  │
                        │  │  health  │  │model_router│  │governance│  │
                        │  │ domain   │  │  domain    │  │  domain  │  │
                        │  │ appl.    │  │  appl.     │  │  appl.   │  │
                        │  │ infra.   │  │  infra.    │  │  infra.  │  │
                        │  └────┬─────┘  └─────┬──────┘  └────┬─────┘  │
                        │       │               │              │        │
                        │  ┌────┴───────────────┴──────────────┴──────┐ │
                        │  │          core/foundation (settings, DB)  │ │
                        │  │          core/contracts  (shared DTOs)   │ │
                        │  └───────────────────────────────────────┬──┘ │
                        └──────────────────────────────────────────│────┘
                                                                   │
                        ┌──────────────────────────────────────────▼────┐
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
                        │    audit_log       (INS+SEL)                  │
                        └───────────────────────────────────────────────┘

  apps/gateway ──────────────────────────────────────────▶  DeepSeek API
  (holds provider credential; no other process does)

  ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄
  Planned (not implemented): Orchestrator, Worker, Runner,
  Workflow Engine, Agent Engine, Memory Engine, Initiative
  Engine, Evaluation Engine, apps/web (PWA)
  ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄
```

| Path | Responsibility |
|---|---|
| `apps/api` | HTTP layer and composition root for health endpoints |
| `apps/gateway` | Privileged process: governance admission, model routing, DeepSeek adapter, retry, circuit breaker, cost recording |
| `core/foundation` | Settings and database engine; no business logic |
| `core/contracts` | Cross-boundary Pydantic DTOs (model router and governance) |
| `core/health` | Readiness and liveness checks |
| `core/model_router` | Tier/capability routing, provider abstraction, usage tracking |
| `core/governance` | Deny-by-default policy evaluation, L0–L4, approval lifecycle, emergency state, audit log |
| `migrations` | Alembic environment and versioned migrations (0001–0011) |
| `docker/postgres/init` | Role and privilege setup on first volume creation |
| `docker/postgres/ensure-roles.sh` | Idempotent role provisioning; runs on every `compose up` before migrations |
| `scripts` | Acceptance test, license check, secret check |

**Stack:** Python 3.12, FastAPI, Uvicorn, pydantic-settings, SQLAlchemy Core (synchronous), Psycopg 3, Alembic, PostgreSQL 18, Docker Compose. Tests use pytest, httpx, and import-linter. Dependencies are locked with uv. The reasoning is in [ADR-0001](docs/adr/0001-phase1-foundation.md).

## Implemented capabilities

### Phase 1 — Foundation
- Modular monolith skeleton: `apps/` transport layer, `core/` DDD-layered modules.
- PostgreSQL with three database roles (`migrator`, `app`, `governance`) and enforced least privilege.
- `GET /health/live` and `GET /health/ready` endpoints.
- Alembic migration pipeline; API never runs migrations.
- 9 import-linter contracts enforcing layer boundaries.
- Acceptance test (`scripts/verify-phase1.sh`): 37 criteria covering roles, DB operations, network exposure, migration cycle, persistence.

### Phase 2 — Model Router and Gateway
- `core/model_router`: tier-based (`fast`/`reason`/`deep`) and capability-based routing, model registry (PostgreSQL-backed, `app` role SELECT only).
- `apps/gateway`: DeepSeek adapter, execution pipeline with max-3-attempt retry and exponential backoff, per-provider circuit breaker (CLOSED → OPEN → HALF-OPEN), streaming support.
- Structured output validation via JSON Schema (`jsonschema`).
- `cost_ledger` table: append-only, records every charge and failed attempt, all arithmetic in `Decimal`.
- `X-Internal-Secret` header authentication on all gateway routes.
- UUIDv7 primary keys via `uuid6`.

### Phase 3 — Governance Engine
- `core/governance/domain`: frozen dataclasses for `Verdict`, `ApprovalRequest`, `Budget`, `EmergencyState`, `PolicyVersion`, `AuditEntry`; `PermissionLevel` (L0–L4), `Decision`, `ApprovalStatus`, `BudgetScope`, `EmergencyLevel` enumerations.
- Deny-by-default policy evaluator: unknown tool → L4/deny; L4 tools always denied regardless of actor.
- Approval lifecycle: `pending → approved → consumed` (or `rejected`/`expired`); single-use, expiring, payload-hash-bound (`SHA-256` of canonical JSON); code-generated risk summaries (no LLM involvement).
- `ConsumeApproval` atomically verifies status, expiry, payload hash, and consumed state in a single DB UPDATE; raises if no row matched.
- SHA-256 hash-chained, append-only `AuditLog` (`previous_row_hash` on every row; first row uses sentinel `sha256("")`).
- `EmergencyState` check: Gateway blocks all requests if any active emergency state exists.
- `GovernancePort` protocol: injected into `ExecutionPipeline`; called before every `execute()` and `stream()` call; `GovernanceDeniedError` is never retried.
- Database role separation: `governance` role provisioned in `docker/postgres/ensure-roles.sh` and idempotent init script; `app` has zero access to all six governance tables.
- 12 import-linter contracts (3 added for governance layering and framework-freedom).

**Deferred in Phase 3 (schema supports, implementation is a stub or placeholder):**
- WebAuthn passkey verification: `passkey_assertion_reference` column exists; actual WebAuthn challenge/response not implemented.
- Git-backed policy storage: `SqlPolicyStore.load_policy()` returns a deny-all stub; `PolicyVersion` table exists.
- `AuthorizedAsset`: deferred to the Cybersecurity phase.
- `verdict.step_id` FK: column is nullable UUID; FK constraint deferred until the `Step` table exists.
- Daily AuditLog chain verification and object-storage export: schema supports it; not scheduled.

## Planned (not yet implemented)

- **Orchestrator** — project registration, requirements analysis, department assignment.
- **Worker** — job queue, lease, heartbeat, agent run loop.
- **Runner** — isolated sandbox execution on a separate host.
- **Workflow Engine** — data-defined execution of stages and gates.
- **Agent Engine** — agent definitions, context building, model/tool loop.
- **Memory Engine** — sourced knowledge storage, retrieval, and promotion.
- **Initiative Engine** — scheduled and event-triggered work discovery.
- **Evaluation Engine** — golden tasks and agent metrics.
- **apps/web** — mobile-first PWA control panel (Emergency Stop, Approval, Inbox, Projects).
- Additional model adapters: OpenAI, Anthropic, local models.
- WebAuthn passkey authentication (full integration).
- Git-backed governance policy storage.
- `AuthorizedAsset` for Cybersecurity scope control.

## Roadmap

- **[Done] Phase 1:** Foundation — modular monolith skeleton, DB roles, health endpoints, acceptance test.
- **[Done] Phase 2:** Model Router — provider abstraction, DeepSeek adapter, circuit breaker, cost ledger.
- **[Done] Phase 3:** Governance Engine — deny-by-default policy, L0–L4, approval lifecycle, audit log.
- **[Upcoming] Phase 4:** Workflow/Worker — job queue, run lifecycle, Step linkage.
- **[Upcoming] Phase 5:** Agent Engine and Orchestrator.
- **[Upcoming] Phase 6:** Web UI, WebAuthn, full policy storage.

### Known limitations

- There is no authentication on `apps/api` health endpoints. No rate limit is applied.
- `SqlPolicyStore.load_policy()` returns a deny-all stub in Phase 3; policy rules are not yet loaded from Git.
- WebAuthn passkey verification is not implemented; `passkey_assertion_reference` is stored but never verified.
- No production deployment is defined. The `runtime` image is built and tested but not published.
- There is no CI yet; test results come from local runs.
- `run_id` and `step_id` in `cost_ledger` are nullable placeholders; populated once the Worker and Step table exist.

## Tests

**Prerequisites: Python environment**

```bash
python3 -m venv .tools/uv && .tools/uv/bin/pip install uv==0.13.6
.tools/uv/bin/uv sync --frozen
```

**Unit tests and static checks**

```bash
.venv/bin/pytest                             # 158 unit tests
.venv/bin/lint-imports --no-cache            # 12 import-boundary contracts
.venv/bin/python scripts/check_licenses.py  # dependency licenses
scripts/check_secrets.sh                    # pattern-based secret check
```

**Integration tests (requires Docker)**

```bash
sudo docker compose up -d --build --wait
sudo docker compose exec -T api pytest -q -p no:cacheprovider tests/integration
```

**Acceptance test**

```bash
scripts/verify-phase1.sh    # 37 isolated criteria; needs sudo and running Docker daemon
```

`verify-phase1.sh` runs in an isolated `aicos-acceptance` Compose project with throwaway secrets. It does not read `.env` and does not touch development volumes. It covers role privileges, database outage and recovery, migration cycle, data persistence, network exposure, and runtime image contents.

| Exit code | Meaning |
|---|---|
| `0` | All criteria passed |
| `1` | At least one criterion failed |
| `2` | Nothing failed, but at least one criterion could not be verified |

The badge reflects the last recorded local run on 2026-11-03: 37 of 37 criteria passed. Unit test count reflects Phase 3 completion (158 tests).

## Migrations

Migrations run in the `migrate` service as the `migrator` role. The API never runs them. Before migrations run, the `ensure_roles` service creates any missing database roles idempotently.

```bash
sudo docker compose run --rm migrate alembic current
sudo docker compose run --rm migrate alembic upgrade head
sudo docker compose run --rm migrate alembic downgrade -1
```

Current migration chain: `0001` (baseline) → `0002` (model_registry) → `0003` (cost_ledger) → `0004` (seed models) → `0005` (policy_version) → `0006` (verdict) → `0007` (approval) → `0008` (budget) → `0009` (emergency_state) → `0010` (audit_log) → `0011` (policy_version INSERT grant fix).

<details>
<summary>Running the Docker daemon manually with systemd</summary>

To keep the daemon from starting at boot:

```bash
sudo systemctl disable --now docker.service docker.socket containerd.service
systemctl is-enabled docker.service docker.socket containerd.service  # each should print "disabled"

sudo systemctl start docker.service                                   # start
sudo systemctl stop docker.service docker.socket containerd.service   # stop completely
systemctl is-active docker.service docker.socket containerd.service   # status
```

- `docker.service` depends on `docker.socket` and `containerd.service`, so starting it brings up both.
- If only `docker.service` is stopped, `docker.socket` stays active and the next `sudo docker` command restarts the daemon.
- The socket is `root:docker 0660`, so a user outside the `docker` group cannot trigger this without `sudo`.
- The package preset for these units is `enabled`, so re-check `is-enabled` after package upgrades.

</details>

## Documentation

| Document | Contents |
|---|---|
| [docs/architecture-and-requirements.md](docs/architecture-and-requirements.md) | Target architecture, trust boundaries, model routing, governance, and requirements |
| [docs/data-model.md](docs/data-model.md) | Conceptual data model and open schema decisions |
| [docs/business-rules.md](docs/business-rules.md) | Workflows, permissions, governance and approval rules |
| [docs/api-spec.md](docs/api-spec.md) | API requirements; most routes and schemas are still undefined |
| [docs/adr/0001-phase1-foundation.md](docs/adr/0001-phase1-foundation.md) | Phase 1 stack and infrastructure decisions |
| [docs/adr/0002-phase2-model-router.md](docs/adr/0002-phase2-model-router.md) | Phase 2 provider abstraction, retry, cost tracking decisions |
| [docs/adr/0003-phase3-governance.md](docs/adr/0003-phase3-governance.md) | Phase 3 governance engine decisions |
| [CLAUDE.md](CLAUDE.md) | Working rules for Claude Code, which is used in this project's development |

## License

This project's own code and documentation are under the [MIT License](LICENSE). Third-party dependencies keep their own licenses and are not relicensed by it; `scripts/check_licenses.py` reports them, and [ADR-0001](docs/adr/0001-phase1-foundation.md) records the non-permissive ones.
