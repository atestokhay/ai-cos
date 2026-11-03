# ADR-0001: Phase 1 Modular Monolith Foundation

- **Status:** Accepted
- **Decided by:** Founder
- **Date:** 2026-11-03
- **Scope:** Phase 1 only. A later ADR may supersede it.

## Context

The documentation defines a single Python codebase, PostgreSQL and the `apps/` + `core/` layout (`architecture §3.1`, `§3.2`). It does not define a framework, driver, migration tool, migration role or health endpoint. This ADR fills only these gaps.

## Decisions

1. **Stack:** Python 3.12, FastAPI, Uvicorn, pydantic-settings, SQLAlchemy Core (synchronous), Psycopg 3, Alembic. Development: pytest, httpx, import-linter. Dependencies are locked with uv and `uv.lock`. `exclude-newer` limits resolution by publication date, so a dependency update also requires moving that date forward.
2. **Infrastructure:** The development environment runs on Docker Engine and the Compose plugin. The user is not added to the `docker` group. The daemon does not start automatically; it is started manually. Images: `postgres:18.6-trixie`, `python:3.12.16-slim-trixie` (verified on Docker Hub on 2026-11-03). Wildcards and `latest` are not used.
3. **Layers:** `apps/*` is the transport layer and composition root. `core/<module>` is split into `domain`, `application` and `infrastructure`. Boundaries are tested automatically with import-linter (`architecture §3.1`).
4. **`core/foundation`:** Shared technical infrastructure. It contains no business logic and cannot import business modules. This ADR adds it to the documented package list.
5. **Database roles:** `postgres` (bootstrap), `migrator` (DDL, not a superuser), `app` (no DDL rights). This ADR adds `migrator` to the documented role list. `governance` and `reporting` are deferred until the processes that use them exist (`architecture §4.1`). CREATE and TEMP are removed from `app` separately. `PUBLIC`'s database and `public` schema privileges are closed for `aicos`, `postgres` and `template1`. `PUBLIC`'s defaults for system catalog reads, function EXECUTE and `plpgsql` USAGE are kept deliberately.
6. **Migrations:** They run in a separate one-shot service as the `migrator` role. The API does not run migrations and does not hold this identity. No default privileges are defined; each migration grants table privileges explicitly.
7. **Health:** `GET /health/live` and `GET /health/ready`, unauthenticated, with a minimal response. These are operational routes and do not establish a project-wide API or error contract.
8. **Environments:** `APP_ENV` separates development and production behavior; debug and API docs are off in production. `compose.yaml` is for development only.
9. **Network:** The API listens on `0.0.0.0:8000` inside the container; the host port is published only on `127.0.0.1`. PostgreSQL publishes no host port.
10. **Acceptance tests:** They run only in the isolated `aicos-acceptance` Compose project. The persistence test table is not part of any migration and does not exist in the development environment.

## Known gaps

- **Rate limiting:** `api-spec §2` and `§5` require a rate limit on every endpoint. The health endpoints have none in Phase 1. This is an unmet requirement; it must be closed during API auth and edge design, and the application must not reach production until it is.
- **Role coverage:** The role separation in `architecture §4.1` is only partly implemented.
- **Role changes:** The init script runs only on an empty volume. No method is defined for changing roles or passwords on existing data.
- **httpx warning:** Starlette 1.10 marks using httpx with `TestClient` as deprecated and recommends `httpx2`. Tests pass; httpx is kept under decision 1, and moving away from it needs a separate decision.

## License review

The project's own code and documentation are MIT licensed (`LICENSE`). This license does not cover third-party dependencies, which remain under their own licenses.

Dependency licenses come from the metadata of installed packages (`scripts/check_licenses.py`). This assessment is a technical record, not legal advice, and must be reviewed again before any product distribution decision.

| Package | License | Use | Assessment |
|---|---|---|---|
| `psycopg`, `psycopg-binary` | LGPL-3.0-only | Runtime | Used unmodified, as a separate library |
| `certifi` | MPL-2.0 | Development only (through `httpx`); not in the runtime image | `REVIEWED` by founder decision (2026-11-03): development dependency only, not in the runtime image |

All other packages are under MIT, BSD, Apache-2.0 or PSF-2.0 licenses.

The `psycopg-binary` wheel contains shared libraries that do not appear separately in its metadata: libpq, OpenSSL (libssl, libcrypto), Kerberos (libkrb5, libgssapi_krb5, libk5crypto, libkrb5support, libcom_err), OpenLDAP (libldap, liblber), Cyrus SASL, libcrypt, libkeyutils, libpcre and libselinux.

**Open item:** The licenses of these libraries have not been verified individually; they must be reviewed before any distribution decision.

## Consequences

- `core` knows nothing about HTTP, so a future `apps/worker` can use the same core with its own composition root. Because the Runner must have no DB access (`architecture §4.2`), this separation must be enforced at that stage.
- The synchronous stack must be re-evaluated when SSE and worker heartbeat requirements arrive.
- This ADR does not turn the conceptual data model into a schema.

## Deferred

Schema (`data-model §10`), Workspace model, API and error contracts, production deployment, `governance` and `reporting` roles, Gateway, Worker, Runner.
